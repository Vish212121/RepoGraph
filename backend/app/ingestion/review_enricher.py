"""Enrich a snapshot with bounded GitHub pull-request review history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.graph.connection import get_graph
from app.ingestion.github_client import GitHubClient
from app.ingestion.loader import GraphLoader


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _person(login: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "id": f"github:user:{login}",
        "provider": "github",
        "login": login,
        "display_name": payload.get("name") or login,
        "identity_source": "github_login",
    }


class ReviewEnricher:
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

    def enrich(self, snapshot_id: str | None = None, pr_limit: int | None = None) -> dict[str, Any]:
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
            raise RuntimeError("No complete snapshot found for review enrichment")
        resolved_id, commit_sha, repository = map(str, rows[0][:3])
        file_rows = self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})-[:CONTAINS_FILE]->(f:File)
            RETURN f.path, f.id
            """,
            {"snapshot_id": resolved_id},
        )
        file_ids = {str(row[0]): str(row[1]) for row in file_rows}
        pull_requests: list[dict[str, Any]] = []
        pull_request_files: list[dict[str, Any]] = []
        reviews: list[dict[str, Any]] = []
        authors: list[dict[str, Any]] = []
        people: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        prs = self.client.list_pull_requests(repository, pr_limit or self.settings.review_pr_limit)
        for payload in prs:
            number = payload.get("number")
            if not number:
                continue
            pr_id = f"github:pull:{repository}:{number}"
            author = payload.get("user") or {}
            login = author.get("login")
            if login:
                people[login] = _person(login, author)
                authors.append({"snapshot_id": resolved_id, "pull_request_id": pr_id, "person_id": people[login]["id"]})
            pull_requests.append(
                {
                    "id": pr_id,
                    "snapshot_id": resolved_id,
                    "number": number,
                    "title": payload.get("title"),
                    "state": payload.get("state"),
                    "draft": bool(payload.get("draft")),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                    "merged_at": payload.get("merged_at"),
                    "head_sha": ((payload.get("head") or {}).get("sha")),
                    "base_sha": ((payload.get("base") or {}).get("sha")),
                    "html_url": payload.get("html_url"),
                    "source_url": payload.get("html_url"),
                }
            )
            try:
                pr_files = self.client.list_pull_request_files(repository, int(number))
                for changed in pr_files:
                    path = changed.get("filename")
                    if path in file_ids:
                        pull_request_files.append(
                            {
                                "snapshot_id": resolved_id,
                                "pull_request_id": pr_id,
                                "file_id": file_ids[path],
                                "path": path,
                                "status": changed.get("status"),
                                "additions": changed.get("additions", 0),
                                "deletions": changed.get("deletions", 0),
                                "source_url": changed.get("blob_url") or payload.get("html_url"),
                            }
                        )
            except Exception as exc:
                warnings.append(f"Could not load files for PR #{number}: {exc}")
            try:
                pr_reviews = self.client.list_pull_request_reviews(repository, int(number))
                for review in pr_reviews:
                    reviewer = review.get("user") or {}
                    reviewer_login = reviewer.get("login")
                    if not reviewer_login or not review.get("id"):
                        continue
                    people[reviewer_login] = _person(reviewer_login, reviewer)
                    reviews.append(
                        {
                            "id": f"github:review:{review['id']}",
                            "snapshot_id": resolved_id,
                            "pull_request_id": pr_id,
                            "person_id": people[reviewer_login]["id"],
                            "review_id": review["id"],
                            "state": review.get("state"),
                            "submitted_at": review.get("submitted_at"),
                            "commit_id": review.get("commit_id"),
                            "html_url": review.get("html_url"),
                            "source_url": review.get("html_url") or payload.get("html_url"),
                            "author_association": review.get("author_association"),
                        }
                    )
            except Exception as exc:
                warnings.append(f"Could not load reviews for PR #{number}: {exc}")

        self.loader.load_reviews(
            pull_requests,
            pull_request_files,
            reviews,
            authors,
            list(people.values()),
            resolved_id,
            _now(),
            warnings,
        )
        return {
            "snapshot_id": resolved_id,
            "repository": repository,
            "commit_sha": commit_sha,
            "pull_requests_scanned": len(pull_requests),
            "review_files_linked": len(pull_request_files),
            "reviews_scanned": len(reviews),
            "review_people": len(people),
            "warnings": warnings[:100],
        }
