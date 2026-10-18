"""Extract bounded, evidence-backed decision candidates from GitHub discussions."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import re
from typing import Any

from app.config import Settings, get_settings
from app.graph.connection import get_graph
from app.ingestion.github_client import GitHubClient
from app.ingestion.loader import GraphLoader


_DECISION_CUES = (
    r"\bwe\s+(?:decided|agreed|will\s+use|chose|choose)\b",
    r"\b(?:the\s+)?(?:chosen|recommended)\s+approach\b",
    r"\b(?:replace|replaced|supersede|superseded|deprecated)\b",
    r"\binstead\s+of\b",
    r"\b(?:decision|design)\s+(?:is|was|will\s+be)\b",
)
_DECISION_PATTERN = re.compile("|".join(_DECISION_CUES), re.IGNORECASE)
_REFERENCE_PATTERN = re.compile(r"(?:(pull\s+request|pr|issue)\s*)?#(\d+)", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _excerpt(value: str | None, limit: int) -> str:
    text = " ".join((value or "").split())
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _candidate_sentences(value: str | None, limit: int) -> list[str]:
    text = value or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    candidates: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = _excerpt(part, limit)
        if len(sentence) >= 20 and _DECISION_PATTERN.search(sentence):
            if sentence not in candidates:
                candidates.append(sentence)
    return candidates[:5]


def _status(statement: str) -> str:
    lowered = statement.casefold()
    if any(word in lowered for word in ("replace", "replaced", "supersede", "superseded", "deprecated")):
        return "superseding"
    if any(word in lowered for word in ("reject", "avoid", "do not use", "don't use")):
        return "rejected"
    if any(word in lowered for word in ("decided", "agreed", "chosen", "chose", "will use")):
        return "adopted"
    return "candidate"


def _confidence(statement: str) -> float:
    lowered = statement.casefold()
    if any(word in lowered for word in ("decided", "agreed", "chosen", "chose", "supersede", "replaced")):
        return 0.9
    return 0.75


def _person(login: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "id": f"github:user:{login}",
        "provider": "github",
        "login": login,
        "display_name": payload.get("name") or login,
        "identity_source": "github_login",
    }


class DecisionEnricher:
    """Fetch bounded discussions and persist conservative decision candidates."""

    def __init__(
        self,
        graph: Any | None = None,
        client: GitHubClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.graph = graph or get_graph(self.settings)
        self.client = client or GitHubClient(self.settings.github_api_base_url, self.settings.github_token)
        self.loader = GraphLoader(self.graph, self.settings.ingest_batch_size)

    def _query(self, query: str, params: dict[str, Any]) -> list[list[Any]]:
        response = self.graph.ro_query(query, params)
        return list(getattr(response, "result_set", []))

    def _snapshot(self, snapshot_id: str | None) -> tuple[str, str, str, set[str], dict[str, str]]:
        rows = self._query(
            """
            MATCH (r:Repository)-[:HAS_SNAPSHOT]->(s:Snapshot)
            WHERE s.status = 'complete' AND ($snapshot_id IS NULL OR s.id = $snapshot_id)
            RETURN s.id, s.commit_sha, r.full_name
            ORDER BY s.captured_at DESC
            LIMIT 1
            """,
            {"snapshot_id": snapshot_id},
        )
        if not rows:
            raise RuntimeError("No complete snapshot found for decision enrichment")
        resolved_id, commit_sha, repository = map(str, rows[0][:3])
        file_rows = self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})-[:CONTAINS_FILE]->(f:File)
            RETURN f.path, f.id
            """,
            {"snapshot_id": resolved_id},
        )
        files = {str(row[0]) for row in file_rows}
        file_ids = {str(row[0]): str(row[1]) for row in file_rows}
        return resolved_id, commit_sha, repository, files, file_ids

    def _comment_records(
        self,
        repository: str,
        snapshot_id: str,
        source_id: str,
        source_type: str,
        source_number: int,
        source_title: str,
        payloads: list[dict[str, Any]],
        file_ids: dict[str, str],
        people: dict[str, dict[str, Any]],
        comments: list[dict[str, Any]],
        comment_sources: list[dict[str, Any]],
        comment_files: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        decision_sources: list[dict[str, Any]],
        decision_evidence: list[dict[str, Any]],
        supersession_refs: list[dict[str, Any]],
    ) -> None:
        for payload in payloads:
            comment_id = payload.get("id")
            body = payload.get("body") or ""
            if not comment_id or not body.strip():
                continue
            author = payload.get("user") or {}
            login = author.get("login")
            comment_key = f"github:comment:{repository}:{comment_id}"
            person_id = None
            if login:
                people[login] = _person(login, author)
                person_id = people[login]["id"]
            comment_url = payload.get("html_url") or f"https://github.com/{repository}/issues/{source_number}"
            comments.append(
                {
                    "id": comment_key,
                    "snapshot_id": snapshot_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "number": source_number,
                    "person_id": person_id,
                    "body_excerpt": _excerpt(body, self.settings.decision_excerpt_length),
                    "content_hash": _hash(body),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                    "html_url": comment_url,
                    "source_url": comment_url,
                }
            )
            comment_sources.append(
                {
                    "snapshot_id": snapshot_id,
                    "comment_id": comment_key,
                    "source_id": source_id,
                    "source_type": source_type,
                }
            )
            for path, file_id in file_ids.items():
                if path in body:
                    comment_files.append({"snapshot_id": snapshot_id, "comment_id": comment_key, "file_id": file_id})
            self._extract_decisions(
                body,
                snapshot_id,
                "comment",
                comment_key,
                source_title,
                comment_url,
                comment_key,
                decisions,
                evidences,
                decision_sources,
                decision_evidence,
                supersession_refs,
            )

    def _extract_decisions(
        self,
        body: str,
        snapshot_id: str,
        source_type: str,
        source_id: str,
        source_title: str,
        source_url: str,
        evidence_source_id: str,
        decisions: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        decision_sources: list[dict[str, Any]],
        decision_evidence: list[dict[str, Any]],
        supersession_refs: list[dict[str, Any]],
    ) -> None:
        for statement in _candidate_sentences(body, self.settings.decision_excerpt_length):
            decision_id = f"github:decision:{_hash(f'{source_id}:{statement}')[:24]}"
            evidence_id = f"github:evidence:{_hash(f'{decision_id}:{statement}')[:24]}"
            decisions.append(
                {
                    "id": decision_id,
                    "snapshot_id": snapshot_id,
                    "topic": source_title,
                    "source_title": source_title,
                    "statement": statement,
                    "status": _status(statement),
                    "confidence": _confidence(statement),
                    "extraction_method": "explicit_cue_phrase",
                    "source_type": source_type,
                    "source_id": source_id,
                    "source_url": source_url,
                    "created_at": _now(),
                    "content_hash": _hash(statement),
                }
            )
            evidences.append(
                {
                    "id": evidence_id,
                    "snapshot_id": snapshot_id,
                    "excerpt": statement,
                    "source_type": source_type,
                    "source_id": evidence_source_id,
                    "source_url": source_url,
                    "confidence": _confidence(statement),
                    "content_hash": _hash(statement),
                }
            )
            decision_sources.append({"snapshot_id": snapshot_id, "decision_id": decision_id, "source_id": source_id, "source_type": source_type})
            decision_evidence.append({"snapshot_id": snapshot_id, "decision_id": decision_id, "evidence_id": evidence_id})
            if _status(statement) == "superseding":
                for match in _REFERENCE_PATTERN.finditer(statement):
                    qualifier, number = match.groups()
                    target_type = "issue" if qualifier and qualifier.casefold() == "issue" else "pull_request"
                    supersession_refs.append(
                        {
                            "snapshot_id": snapshot_id,
                            "decision_id": decision_id,
                            "target_source_id": f"github:{'issue' if target_type == 'issue' else 'pull'}:{source_id.split(':')[2]}:{number}",
                            "target_source_type": target_type,
                        }
                    )

    def enrich(self, snapshot_id: str | None = None, source_limit: int | None = None) -> dict[str, Any]:
        resolved_id, commit_sha, repository, _, file_ids = self._snapshot(snapshot_id)
        limit = source_limit or self.settings.decision_source_limit
        pull_requests = self.client.list_pull_requests(repository, limit)
        issues = [item for item in self.client.list_issues(repository, limit) if not item.get("pull_request")]
        people: dict[str, dict[str, Any]] = {}
        issue_rows: list[dict[str, Any]] = []
        comments: list[dict[str, Any]] = []
        comment_sources: list[dict[str, Any]] = []
        comment_files: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        evidences: list[dict[str, Any]] = []
        decision_sources: list[dict[str, Any]] = []
        decision_evidence: list[dict[str, Any]] = []
        supersession_refs: list[dict[str, Any]] = []
        warnings: list[str] = []

        for payload, source_type, source_id in [
            *[(item, "pull_request", f"github:pull:{repository}:{item.get('number')}") for item in pull_requests],
            *[(item, "issue", f"github:issue:{repository}:{item.get('number')}") for item in issues],
        ]:
            number = payload.get("number")
            if not number:
                continue
            title = payload.get("title") or f"{source_type} #{number}"
            source_url = payload.get("html_url") or f"https://github.com/{repository}/{'pull' if source_type == 'pull_request' else 'issues'}/{number}"
            if source_type == "issue":
                issue_rows.append(
                    {
                        "id": source_id,
                        "snapshot_id": resolved_id,
                        "number": number,
                        "title": title,
                        "state": payload.get("state"),
                        "created_at": payload.get("created_at"),
                        "updated_at": payload.get("updated_at"),
                        "html_url": source_url,
                        "source_url": source_url,
                        "body_excerpt": _excerpt(payload.get("body"), self.settings.decision_excerpt_length),
                        "content_hash": _hash(payload.get("body") or ""),
                    }
                )
            self._extract_decisions(
                payload.get("body") or "",
                resolved_id,
                source_type,
                source_id,
                title,
                source_url,
                source_id,
                decisions,
                evidences,
                decision_sources,
                decision_evidence,
                supersession_refs,
            )
            try:
                source_comments = self.client.list_issue_comments(repository, int(number), self.settings.decision_comment_limit)
                self._comment_records(
                    repository,
                    resolved_id,
                    source_id,
                    source_type,
                    int(number),
                    title,
                    source_comments,
                    file_ids,
                    people,
                    comments,
                    comment_sources,
                    comment_files,
                    decisions,
                    evidences,
                    decision_sources,
                    decision_evidence,
                    supersession_refs,
                )
            except Exception as exc:
                warnings.append(f"Could not load comments for {source_type} #{number}: {exc}")

        self.loader.load_decisions(
            issue_rows,
            comments,
            decisions,
            evidences,
            people=list(people.values()),
            comment_sources=comment_sources,
            comment_files=comment_files,
            decision_sources=decision_sources,
            decision_evidence=decision_evidence,
            supersession_refs=supersession_refs,
            snapshot_id=resolved_id,
            enriched_at=_now(),
            warnings=warnings,
        )
        return {
            "snapshot_id": resolved_id,
            "repository": repository,
            "commit_sha": commit_sha,
            "issues_scanned": len(issue_rows),
            "comments_scanned": len(comments),
            "decisions_extracted": len(decisions),
            "evidence_records": len(evidences),
            "decision_people": len(people),
            "warnings": warnings[:100],
        }
