"""Whitelisted, read-only FalkorDB queries for RepoBrain reasoning."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import re
from typing import Any

from app.config import Settings, get_settings
from app.evidence.models import EvidenceBundle
from app.graph.connection import get_graph
from app.memory.models import FindingCreate, FindingUpdate
from app.memory.repository import MemoryRepository


_DECISION_STOP_WORDS = {
    "why", "what", "which", "when", "where", "was", "were", "is", "are", "the", "a", "an",
    "this", "that", "current", "earlier", "decision", "decisions", "design", "approach", "chosen",
    "replaced", "replace", "repository", "project", "use", "used", "using", "does", "did", "for",
    "with", "from", "about", "and", "or", "to", "of", "in", "on", "it", "we", "they",
}


def _decision_terms(topic: str) -> list[str]:
    terms = re.findall(r"[a-z0-9_./-]+", topic.casefold())
    return sorted({term for term in terms if len(term) >= 3 and term not in _DECISION_STOP_WORDS})[:12]


class GraphQueryError(RuntimeError):
    """Raised when graph evidence cannot be obtained safely."""


class GraphQueryTools:
    """Expose bounded graph operations instead of arbitrary model-generated Cypher."""

    def __init__(self, graph: Any | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.graph = graph or get_graph(self.settings)
        self.memory = MemoryRepository(self.graph, settings=self.settings)

    @staticmethod
    def _text(value: str, field_name: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must not be empty")
        return value

    @staticmethod
    def _limit(value: int) -> int:
        if value < 1:
            raise ValueError("limit must be positive")
        return min(value, 100)

    @staticmethod
    def _column_name(column: Any) -> str:
        """Normalize FalkorDB's header entries across client response formats."""

        if isinstance(column, (list, tuple)) and len(column) >= 2:
            return str(column[1])
        return str(column)

    def _execute(
        self,
        tool_name: str,
        query: str,
        parameters: dict[str, Any],
        snapshot_id: str | None,
        snapshot_selector_query: str | None = None,
        result_type: str = "verified",
        warnings: list[str] | None = None,
    ) -> EvidenceBundle:
        response = self.graph.ro_query(query, parameters)
        raw_rows = list(getattr(response, "result_set", []))
        columns = [self._column_name(column) for column in getattr(response, "header", [])]
        if raw_rows and not columns:
            raise GraphQueryError(f"{tool_name} returned rows without column metadata")
        rows = [dict(zip(columns, row, strict=False)) for row in raw_rows]
        source_urls: list[str] = []

        def collect_urls(value: Any) -> list[str]:
            if isinstance(value, str):
                return [value]
            if isinstance(value, (list, tuple, set)):
                urls: list[str] = []
                for item in value:
                    urls.extend(collect_urls(item))
                return urls
            return []

        for row in rows:
            for key, value in row.items():
                if value and (key.endswith("_url") or key.endswith("_urls") or key == "source_url"):
                    for url in collect_urls(value):
                        if url not in source_urls:
                            source_urls.append(url)
        return EvidenceBundle(
            tool_name=tool_name,
            query=query.strip(),
            parameters=parameters,
            columns=columns,
            rows=rows,
            snapshot_id=snapshot_id,
            source_urls=source_urls,
            snapshot_selector_query=snapshot_selector_query,
            result_type=result_type,
            warnings=warnings or [],
        )

    def resolve_snapshot(self, snapshot_id: str | None = None) -> tuple[str, str, list[str]]:
        """Resolve one complete snapshot and return its ID, query, and parameters."""

        query = """
        MATCH (s:Snapshot)
        WHERE s.status = 'complete'
          AND ($snapshot_id IS NULL OR s.id = $snapshot_id)
        RETURN s.id AS snapshot_id
        ORDER BY s.captured_at DESC
        LIMIT 1
        """
        parameters: dict[str, Any] = {"snapshot_id": snapshot_id}
        response = self.graph.ro_query(query, parameters)
        rows = list(getattr(response, "result_set", []))
        if not rows or not rows[0] or not rows[0][0]:
            requested = snapshot_id or "the latest complete snapshot"
            raise GraphQueryError(f"No complete snapshot found for {requested}")
        return str(rows[0][0]), query.strip(), [str(value) for value in parameters.values()]

    def snapshot_overview(self, snapshot_id: str | None = None) -> EvidenceBundle:
        """Return repository and snapshot metadata for one complete snapshot."""

        query = """
        MATCH (r:Repository)-[:HAS_SNAPSHOT]->(s:Snapshot)
        WHERE s.status = 'complete'
          AND ($snapshot_id IS NULL OR s.id = $snapshot_id)
        RETURN r.full_name AS repository,
               r.html_url AS repository_url,
               s.id AS snapshot_id,
               s.commit_sha AS commit_sha,
               s.captured_at AS captured_at,
               s.file_count AS file_count,
               s.commit_count AS commit_count,
               s.source_url AS snapshot_url
        ORDER BY s.captured_at DESC
        LIMIT 1
        """
        parameters = {"snapshot_id": snapshot_id}
        evidence = self._execute("snapshot_overview", query, parameters, snapshot_id)
        if evidence.snapshot_id is None and evidence.rows:
            discovered_id = evidence.rows[0].get("snapshot_id")
            if discovered_id:
                evidence = replace(evidence, snapshot_id=str(discovered_id))
        return evidence

    def list_snapshots(self, limit: int = 20) -> EvidenceBundle:
        """List complete snapshots for the UI snapshot selector."""

        limit = self._limit(limit)
        query = """
        MATCH (r:Repository)-[:HAS_SNAPSHOT]->(s:Snapshot)
        WHERE s.status = 'complete'
        RETURN r.full_name AS repository,
               r.html_url AS repository_url,
               s.id AS snapshot_id,
               s.commit_sha AS commit_sha,
               s.captured_at AS captured_at,
               s.file_count AS file_count,
               s.commit_count AS commit_count,
               s.source_url AS snapshot_url
        ORDER BY s.captured_at DESC
        LIMIT $limit
        """
        return self._execute("list_snapshots", query, {"limit": limit}, None)

    def contributor_changes(
        self,
        contributor: str,
        snapshot_id: str | None = None,
        limit: int = 20,
    ) -> EvidenceBundle:
        """Find files changed by an authored commit from a contributor."""

        contributor = self._text(contributor, "contributor")
        limit = self._limit(limit)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_COMMIT]->(c:Commit)-[ch:CHANGED]->(f:File),
              (c)-[:AUTHORED_BY]->(p:Person)
        WHERE s.id = $snapshot_id
          AND (toLower(p.login) = toLower($contributor)
               OR toLower(p.display_name) = toLower($contributor))
        RETURN p.login AS contributor,
               p.display_name AS display_name,
               c.sha AS commit_sha,
               c.subject AS commit_subject,
               c.authored_at AS authored_at,
               f.path AS file_path,
               ch.status AS change_status,
               ch.additions AS additions,
               ch.deletions AS deletions,
               c.html_url AS commit_url,
               f.source_url AS file_url
        ORDER BY c.authored_at DESC, f.path
        LIMIT $limit
        """
        parameters = {"snapshot_id": resolved_id, "contributor": contributor, "limit": limit}
        return self._execute("contributor_changes", query, parameters, resolved_id, selector)

    def file_contributors(
        self,
        path_fragment: str,
        snapshot_id: str | None = None,
        limit: int = 20,
    ) -> EvidenceBundle:
        """Find contributors connected to files matching a path fragment."""

        path_fragment = self._text(path_fragment, "path_fragment")
        limit = self._limit(limit)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_FILE]->(f:File),
              (s)-[:CONTAINS_COMMIT]->(c:Commit)-[:CHANGED]->(f),
              (c)-[:AUTHORED_BY]->(p:Person)
        WHERE s.id = $snapshot_id
          AND toLower(f.path) CONTAINS toLower($path_fragment)
        RETURN p.login AS contributor,
               p.display_name AS display_name,
               count(DISTINCT c) AS commit_count,
               collect(DISTINCT f.path) AS file_paths,
               collect(DISTINCT f.source_url) AS file_urls,
               min(c.authored_at) AS first_authored_at,
               max(c.authored_at) AS last_authored_at
        ORDER BY commit_count DESC, contributor
        LIMIT $limit
        """
        parameters = {"snapshot_id": resolved_id, "path_fragment": path_fragment, "limit": limit}
        evidence = self._execute("file_contributors", query, parameters, resolved_id, selector)
        if not evidence.rows:
            return evidence

        # Keep the contributor summary compact, but attach the commit/file rows
        # needed to explain what each contributor actually changed. These rows
        # are returned as verified supporting evidence rather than synthesized
        # prose, so the UI can render a readable change timeline.
        change_query = """
        MATCH (s:Snapshot)-[:CONTAINS_COMMIT]->(c:Commit)-[ch:CHANGED]->(f:File),
              (c)-[:AUTHORED_BY]->(p:Person)
        WHERE s.id = $snapshot_id
          AND toLower(f.path) CONTAINS toLower($path_fragment)
        RETURN f.path AS file_path,
               c.sha AS commit_sha,
               c.subject AS commit_subject,
               c.message AS commit_message,
               c.authored_at AS authored_at,
               p.login AS contributor,
               p.display_name AS display_name,
               ch.status AS change_status,
               ch.additions AS additions,
               ch.deletions AS deletions,
               c.html_url AS commit_url,
               f.source_url AS file_url
        ORDER BY c.authored_at DESC, f.path
        LIMIT $change_limit
        """
        change_parameters = {
            "snapshot_id": resolved_id,
            "path_fragment": path_fragment,
            "change_limit": min(limit * 5, 100),
        }
        changes = self._execute(
            "file_change_details",
            change_query,
            change_parameters,
            resolved_id,
            selector,
        )
        source_urls = list(evidence.source_urls)
        for url in changes.source_urls:
            if url not in source_urls:
                source_urls.append(url)
        return replace(
            evidence,
            source_urls=source_urls,
            derived_results=changes.rows,
        )

    def file_history(
        self,
        path_fragment: str,
        snapshot_id: str | None = None,
        limit: int = 30,
    ) -> EvidenceBundle:
        """Trace commits and authors connected to matching files."""

        path_fragment = self._text(path_fragment, "path_fragment")
        limit = self._limit(limit)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_COMMIT]->(c:Commit)-[ch:CHANGED]->(f:File),
              (c)-[:AUTHORED_BY]->(p:Person)
        WHERE s.id = $snapshot_id
          AND toLower(f.path) CONTAINS toLower($path_fragment)
        RETURN f.path AS file_path,
               c.sha AS commit_sha,
               c.subject AS commit_subject,
               c.authored_at AS authored_at,
               p.login AS contributor,
               ch.status AS change_status,
               ch.additions AS additions,
               ch.deletions AS deletions,
               c.html_url AS commit_url,
               f.source_url AS file_url
        ORDER BY c.authored_at DESC
        LIMIT $limit
        """
        parameters = {"snapshot_id": resolved_id, "path_fragment": path_fragment, "limit": limit}
        return self._execute("file_history", query, parameters, resolved_id, selector)

    def file_change_detail(
        self,
        path_fragment: str,
        snapshot_id: str | None = None,
        limit: int = 10,
    ) -> EvidenceBundle:
        """Return bounded, line-level GitHub patch evidence for matching files."""

        path_fragment = self._text(path_fragment, "path_fragment")
        limit = min(self._limit(limit), 20)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_COMMIT]->(c:Commit)-[ch:CHANGED]->(f:File),
              (c)-[:AUTHORED_BY]->(p:Person)
        WHERE s.id = $snapshot_id
          AND toLower(f.path) CONTAINS toLower($path_fragment)
        RETURN f.path AS file_path,
               c.sha AS commit_sha,
               c.subject AS commit_subject,
               c.message AS commit_message,
               c.authored_at AS authored_at,
               p.login AS contributor,
               p.display_name AS display_name,
               ch.status AS change_status,
               ch.previous_path AS previous_path,
               ch.additions AS additions,
               ch.deletions AS deletions,
               ch.patch AS patch,
               ch.patch_available AS patch_available,
               ch.patch_truncated AS patch_truncated,
               ch.patch_char_count AS patch_char_count,
               c.html_url AS commit_url,
               f.source_url AS file_url
        ORDER BY c.authored_at DESC, f.path
        LIMIT $limit
        """
        parameters = {"snapshot_id": resolved_id, "path_fragment": path_fragment, "limit": limit}
        return self._execute("file_change_detail", query, parameters, resolved_id, selector)

    def commit_impact(
        self,
        commit_prefix: str,
        snapshot_id: str | None = None,
        limit: int = 50,
    ) -> EvidenceBundle:
        """Find files affected by a commit SHA or unique SHA prefix."""

        commit_prefix = self._text(commit_prefix, "commit_prefix")
        limit = self._limit(limit)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_COMMIT]->(c:Commit)-[ch:CHANGED]->(f:File)
        WHERE s.id = $snapshot_id
          AND c.sha STARTS WITH $commit_prefix
        RETURN c.sha AS commit_sha,
               c.subject AS commit_subject,
               c.authored_at AS authored_at,
               f.path AS file_path,
               ch.status AS change_status,
               ch.additions AS additions,
               ch.deletions AS deletions,
               c.html_url AS commit_url,
               f.source_url AS file_url
        ORDER BY f.path
        LIMIT $limit
        """
        parameters = {"snapshot_id": resolved_id, "commit_prefix": commit_prefix, "limit": limit}
        return self._execute("commit_impact", query, parameters, resolved_id, selector)

    def impact_analysis(
        self,
        file_path: str,
        snapshot_id: str | None = None,
        max_hops: int = 3,
        limit: int = 25,
    ) -> EvidenceBundle:
        """Find reverse static dependents of a file within one snapshot."""

        file_path = self._text(file_path, "file_path")
        if max_hops < 1 or max_hops > 5:
            raise ValueError("max_hops must be between 1 and 5")
        limit = self._limit(limit)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = f"""
        MATCH (s:Snapshot)-[:CONTAINS_FILE]->(target:File)
        MATCH p=(dependent:File)-[:DEPENDS_ON*1..{max_hops}]->(target)
        WHERE s.id = $snapshot_id
          AND target.path = $file_path
          AND dependent.path <> target.path
        WITH dependent, target, p
        ORDER BY dependent.path, length(p)
        WITH dependent,
             target.source_url AS target_file_url,
             collect([
                 length(p),
                 [n IN nodes(p) | n.path],
                 [r IN relationships(p) | r.edge_type]
             ])[0] AS shortest_path
        RETURN dependent.path AS affected_file,
               shortest_path[0] AS hop_distance,
               shortest_path[1] AS witness_path,
               shortest_path[2] AS edge_types,
               dependent.source_url AS affected_file_url,
               target_file_url
        ORDER BY hop_distance, affected_file
        LIMIT $limit
        """
        parameters = {
            "snapshot_id": resolved_id,
            "file_path": file_path,
            "limit": limit,
        }
        return self._execute(
            "impact_analysis",
            query,
            parameters,
            resolved_id,
            selector,
            result_type="derived",
            warnings=[
                "Dependency edges are statically extracted from Python imports; runtime and dynamic imports are not verified."
            ],
        )

    def trace_decision(
        self,
        topic: str,
        snapshot_id: str | None = None,
        limit: int = 10,
    ) -> EvidenceBundle:
        """Return decision candidates and their source evidence for a topic."""

        topic = self._text(topic, "topic")
        topic_terms = _decision_terms(topic)
        if not topic_terms:
            raise ValueError("topic must contain at least one searchable term")
        limit = self._limit(limit)
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_DECISION]->(d:Decision)
        WHERE s.id = $snapshot_id
          AND ANY(term IN $topic_terms WHERE
              toLower(coalesce(d.topic, '')) CONTAINS term OR
              toLower(coalesce(d.source_title, '')) CONTAINS term OR
              toLower(coalesce(d.statement, '')) CONTAINS term)
        OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(e:Evidence)
        OPTIONAL MATCH (d)-[:SUPERSEDES]->(older:Decision)
        RETURN d.id AS decision_id,
               d.topic AS topic,
               d.source_title AS source_title,
               d.statement AS statement,
               d.status AS status,
               d.confidence AS confidence,
               d.extraction_method AS extraction_method,
               d.source_type AS source_type,
               d.source_id AS source_id,
               d.source_url AS source_url,
               d.created_at AS created_at,
               collect(DISTINCT e.excerpt) AS evidence_excerpts,
               collect(DISTINCT e.source_url) AS evidence_urls,
               collect(DISTINCT older.statement) AS superseded_statements
        ORDER BY confidence DESC, created_at DESC
        LIMIT $limit
        """
        parameters = {
            "snapshot_id": resolved_id,
            "topic": topic,
            "topic_terms": topic_terms,
            "limit": limit,
        }
        return self._execute(
            "trace_decision",
            query,
            parameters,
            resolved_id,
            selector,
            result_type="derived",
            warnings=[
                "Decision results are candidates extracted from explicit discussion cue phrases; they are not authoritative architectural records by themselves.",
                "Supersession is reported only when an explicit source reference produced a graph relationship.",
            ],
        )

    def recall_context(
        self,
        tenant_id: str,
        query: str,
        snapshot_id: str | None = None,
        limit: int = 10,
    ) -> EvidenceBundle:
        return self.memory.recall_context(tenant_id, query, snapshot_id, limit)

    def create_finding(self, tenant_id: str, payload: FindingCreate) -> dict[str, Any]:
        return self.memory.create_finding(tenant_id, payload)

    def update_finding(self, tenant_id: str, finding_id: str, payload: FindingUpdate) -> dict[str, Any]:
        return self.memory.update_finding(tenant_id, finding_id, payload)

    def suggest_reviewers(
        self,
        file_paths: list[str],
        snapshot_id: str | None = None,
        limit: int = 5,
        exclude_logins: list[str] | None = None,
    ) -> EvidenceBundle:
        """Rank contributors by transparent file-change familiarity signals."""

        if not file_paths:
            raise ValueError("file_paths must contain at least one path")
        normalized_paths = sorted({self._text(path, "file_path") for path in file_paths})
        if len(normalized_paths) > 50:
            raise ValueError("file_paths cannot contain more than 50 paths")
        limit = self._limit(limit)
        excluded = sorted({login.strip().lower() for login in (exclude_logins or []) if login.strip()})
        resolved_id, selector, _ = self.resolve_snapshot(snapshot_id)
        query = """
        MATCH (s:Snapshot)-[:CONTAINS_COMMIT]->(c:Commit)-[:CHANGED]->(f:File),
              (c)-[:AUTHORED_BY]->(p:Person)
        WHERE s.id = $snapshot_id
          AND f.path IN $file_paths
          AND p.login IS NOT NULL
          AND NOT toLower(p.login) CONTAINS 'bot'
          AND NOT toLower(p.login) IN $exclude_logins
        RETURN p.login AS contributor,
               p.display_name AS display_name,
               count(DISTINCT f) AS covered_files,
               count(DISTINCT c) AS commit_count,
               collect(DISTINCT f.path) AS file_paths,
               collect(DISTINCT c.sha) AS commit_shas,
               collect(DISTINCT c.html_url) AS commit_urls,
               collect(DISTINCT f.source_url) AS file_urls,
               max(c.authored_at) AS last_authored_at,
               s.captured_at AS snapshot_captured_at
        ORDER BY covered_files DESC, last_authored_at DESC, contributor
        LIMIT $limit
        """
        parameters = {
            "snapshot_id": resolved_id,
            "file_paths": normalized_paths,
            "exclude_logins": excluded,
            "limit": limit,
        }
        evidence = self._execute(
            "suggest_reviewers",
            query,
            parameters,
            resolved_id,
            selector,
            result_type="derived",
            warnings=[
                "Recommendations combine authored file-change history with verified review history when available.",
                "Bot exclusion is based on login-name heuristics and may be incomplete.",
            ],
        )
        review_query = """
        MATCH (s:Snapshot)-[:CONTAINS_PULL_REQUEST]->(pr:PullRequest)-[:CHANGES]->(f:File),
              (review:Review)-[:ON]->(pr),
              (reviewer:Person)-[:SUBMITTED_REVIEW]->(review)
        WHERE s.id = $snapshot_id
          AND f.path IN $file_paths
          AND reviewer.login IS NOT NULL
          AND NOT toLower(reviewer.login) CONTAINS 'bot'
          AND NOT toLower(reviewer.login) IN $exclude_logins
        RETURN reviewer.login AS contributor,
               reviewer.display_name AS display_name,
               count(DISTINCT review) AS review_count,
               collect(DISTINCT CASE WHEN review.state = 'APPROVED' THEN review.id ELSE null END) AS approval_review_ids,
               collect(DISTINCT CASE WHEN review.state = 'CHANGES_REQUESTED' THEN review.id ELSE null END) AS changes_requested_review_ids,
               collect(DISTINCT f.path) AS reviewed_file_paths,
               collect(DISTINCT review.html_url) AS review_urls,
               max(review.submitted_at) AS last_reviewed_at,
               s.captured_at AS snapshot_captured_at
        ORDER BY review_count DESC, last_reviewed_at DESC, contributor
        LIMIT $review_limit
        """
        review_parameters = {**parameters, "review_limit": 100}
        review_response = self.graph.ro_query(review_query, review_parameters)
        review_columns = [self._column_name(column) for column in getattr(review_response, "header", [])]
        review_rows = [dict(zip(review_columns, row, strict=False)) for row in getattr(review_response, "result_set", [])]
        by_login = {str(row.get("contributor")): row for row in evidence.rows if row.get("contributor")}
        for review_row in review_rows:
            login = str(review_row.get("contributor"))
            row = by_login.setdefault(login, {"contributor": login, "display_name": review_row.get("display_name")})
            for key in (
                "review_count", "approval_review_ids", "changes_requested_review_ids", "reviewed_file_paths",
                "review_urls", "last_reviewed_at", "snapshot_captured_at",
            ):
                row[key] = review_row.get(key)
        merged_rows = list(by_login.values())
        all_columns = list(evidence.columns)
        for row in merged_rows:
            for key in row:
                if key not in all_columns:
                    all_columns.append(key)
        source_urls = list(evidence.source_urls)
        for row in review_rows:
            for url in row.get("review_urls") or []:
                if url and url not in source_urls:
                    source_urls.append(url)
        evidence = replace(
            evidence,
            rows=merged_rows,
            columns=all_columns,
            source_urls=source_urls,
            query=f"{query.strip()}\n\n-- REVIEW HISTORY QUERY --\n{review_query.strip()}",
            parameters=review_parameters,
        )
        snapshot_time = next(
            (_parse_timestamp(row.get("snapshot_captured_at")) for row in merged_rows if row.get("snapshot_captured_at")),
            None,
        )
        for row in merged_rows:
            covered = int(row.get("covered_files") or 0)
            commits = int(row.get("commit_count") or 0)
            reviewed_paths = set(row.get("reviewed_file_paths") or [])
            review_count = int(row.get("review_count") or 0)
            approvals = len({item for item in (row.get("approval_review_ids") or []) if item})
            changes_requested = len({item for item in (row.get("changes_requested_review_ids") or []) if item})
            coverage_score = round(covered / len(normalized_paths), 4)
            review_overlap_score = round(len(reviewed_paths) / len(normalized_paths), 4)
            authored_at = _parse_timestamp(row.get("last_authored_at"))
            reviewed_at = _parse_timestamp(row.get("last_reviewed_at"))
            latest_activity = reviewed_at or authored_at
            age_days = max(0.0, (snapshot_time - latest_activity).total_seconds() / 86_400) if snapshot_time and latest_activity else 3650.0
            recency_score = round(1 / (1 + age_days / 180), 4)
            approval_activity_score = round(min(approvals / 5, 1.0), 4)
            authored_change_score = round(min(commits / 10, 1.0), 4)
            row["covered_files"] = covered
            row["commit_count"] = commits
            row["review_count"] = review_count
            row["approval_count"] = approvals
            row["changes_requested_count"] = changes_requested
            row["coverage_score"] = coverage_score
            row["review_overlap_score"] = review_overlap_score
            row["review_recency_score"] = recency_score if reviewed_at else 0.0
            row["recency_score"] = recency_score
            row["activity_score"] = authored_change_score
            row["approval_activity_score"] = approval_activity_score
            row["authored_change_score"] = authored_change_score
            row["final_score"] = round(
                0.35 * coverage_score
                + 0.30 * review_overlap_score
                + 0.20 * recency_score
                + 0.10 * approval_activity_score
                + 0.05 * authored_change_score,
                4,
            )
            row["requested_file_count"] = len(normalized_paths)
        merged_rows.sort(key=lambda row: (-float(row.get("final_score", 0)), str(row.get("contributor", ""))))
        evidence = replace(evidence, rows=merged_rows[:limit])
        return evidence


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
