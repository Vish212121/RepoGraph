"""Idempotent, snapshot-scoped writes into FalkorDB."""

from __future__ import annotations

from typing import Any, Iterable

from app.graph.connection import get_graph
from app.ingestion.models import SnapshotData


class GraphLoader:
    """Load one normalized snapshot without exposing incomplete data."""

    def __init__(self, graph: Any | None = None, batch_size: int = 100) -> None:
        self.graph = graph or get_graph()
        self.batch_size = batch_size

    def _query(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return self.graph.query(query, params or {})

    def _batches(self, rows: Iterable[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
        batch: list[dict[str, Any]] = []
        for row in rows:
            batch.append(row)
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _load_batches(self, rows: list[dict[str, Any]], query: str) -> None:
        for batch in self._batches(rows):
            self._query(query, {"rows": batch})

    def _mark_status(self, snapshot_id: str, status: str, error: str | None = None) -> None:
        self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})
            SET s.status = $status,
                s.error = $error
            """,
            {"snapshot_id": snapshot_id, "status": status, "error": error},
        )

    def load_dependencies(
        self,
        rows: list[dict[str, Any]],
        snapshot_id: str,
        extracted_at: str,
        warnings: list[str],
    ) -> None:
        """Replace this snapshot's derived dependency edges idempotently."""

        self._query(
            """
            MATCH (source:File)-[rel:DEPENDS_ON {snapshot_id: $snapshot_id}]->(target:File)
            DELETE rel
            """,
            {"snapshot_id": snapshot_id},
        )
        self._load_batches(
            rows,
            """
            UNWIND $rows AS row
            MATCH (source:File {id: row.source_file_id}), (target:File {id: row.target_file_id})
            MERGE (source)-[rel:DEPENDS_ON {
                snapshot_id: row.snapshot_id,
                source_file_id: row.source_file_id,
                target_file_id: row.target_file_id
            }]->(target)
            SET rel.import_name = row.import_name,
                rel.edge_type = row.edge_type,
                rel.confidence = row.confidence,
                rel.evidence_level = row.evidence_level,
                rel.source_url = row.source_url,
                rel.content_sha = row.content_sha,
                rel.extracted_at = row.extracted_at
            """,
        )
        self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})
            SET s.dependency_edge_count = $edge_count,
                s.dependency_extracted_at = $extracted_at,
                s.dependency_warnings = $warnings
            """,
            {
                "snapshot_id": snapshot_id,
                "edge_count": len(rows),
                "extracted_at": extracted_at,
                "warnings": warnings[:100],
            },
        )

    def load_reviews(
        self,
        pull_requests: list[dict[str, Any]],
        pull_request_files: list[dict[str, Any]],
        reviews: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        people: list[dict[str, Any]],
        snapshot_id: str,
        enriched_at: str,
        warnings: list[str],
    ) -> None:
        """Replace this snapshot's PR and review enrichment idempotently."""

        self._query(
            """
            MATCH (review:Review {snapshot_id: $snapshot_id})
            DETACH DELETE review
            """,
            {"snapshot_id": snapshot_id},
        )
        self._query(
            """
            MATCH (pr:PullRequest {snapshot_id: $snapshot_id})
            DETACH DELETE pr
            """,
            {"snapshot_id": snapshot_id},
        )
        self._load_batches(
            people,
            """
            UNWIND $rows AS row
            MERGE (p:Person {id: row.id})
            SET p.provider = row.provider,
                p.login = row.login,
                p.display_name = row.display_name,
                p.identity_source = row.identity_source
            """,
        )
        self._load_batches(
            pull_requests,
            """
            UNWIND $rows AS row
            MERGE (pr:PullRequest {id: row.id})
            SET pr.snapshot_id = row.snapshot_id,
                pr.number = row.number,
                pr.title = row.title,
                pr.state = row.state,
                pr.draft = row.draft,
                pr.created_at = row.created_at,
                pr.updated_at = row.updated_at,
                pr.merged_at = row.merged_at,
                pr.head_sha = row.head_sha,
                pr.base_sha = row.base_sha,
                pr.html_url = row.html_url,
                pr.source_url = row.source_url
            """,
        )
        self._load_batches(
            [{"snapshot_id": snapshot_id, "pull_request_id": row["id"]} for row in pull_requests],
            """
            UNWIND $rows AS row
            MATCH (s:Snapshot {id: row.snapshot_id}), (pr:PullRequest {id: row.pull_request_id})
            MERGE (s)-[:CONTAINS_PULL_REQUEST {snapshot_id: row.snapshot_id}]->(pr)
            """,
        )
        self._load_batches(
            authors,
            """
            UNWIND $rows AS row
            MATCH (pr:PullRequest {id: row.pull_request_id}), (p:Person {id: row.person_id})
            MERGE (p)-[:AUTHORED_PULL_REQUEST {snapshot_id: row.snapshot_id}]->(pr)
            """,
        )
        self._load_batches(
            pull_request_files,
            """
            UNWIND $rows AS row
            MATCH (pr:PullRequest {id: row.pull_request_id}), (f:File {id: row.file_id})
            MERGE (pr)-[rel:CHANGES {snapshot_id: row.snapshot_id, file_id: row.file_id}]->(f)
            SET rel.status = row.status,
                rel.additions = row.additions,
                rel.deletions = row.deletions,
                rel.source_url = row.source_url
            """,
        )
        self._load_batches(
            reviews,
            """
            UNWIND $rows AS row
            MATCH (pr:PullRequest {id: row.pull_request_id}), (p:Person {id: row.person_id})
            MERGE (review:Review {id: row.id})
            SET review.snapshot_id = row.snapshot_id,
                review.review_id = row.review_id,
                review.state = row.state,
                review.submitted_at = row.submitted_at,
                review.commit_id = row.commit_id,
                review.html_url = row.html_url,
                review.source_url = row.source_url,
                review.author_association = row.author_association
            MERGE (review)-[:ON {snapshot_id: row.snapshot_id}]->(pr)
            MERGE (p)-[:SUBMITTED_REVIEW {snapshot_id: row.snapshot_id}]->(review)
            """,
        )
        self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})
            SET s.review_enriched_at = $enriched_at,
                s.pull_request_count = $pull_request_count,
                s.review_count = $review_count,
                s.review_warnings = $warnings
            """,
            {
                "snapshot_id": snapshot_id,
                "enriched_at": enriched_at,
                "pull_request_count": len(pull_requests),
                "review_count": len(reviews),
                "warnings": warnings[:100],
            },
        )

    def load_decisions(
        self,
        issues: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        people: list[dict[str, Any]],
        comment_sources: list[dict[str, Any]],
        comment_files: list[dict[str, Any]],
        decision_sources: list[dict[str, Any]],
        decision_evidence: list[dict[str, Any]],
        supersession_refs: list[dict[str, Any]],
        snapshot_id: str,
        enriched_at: str,
        warnings: list[str],
    ) -> None:
        """Replace one snapshot's decision-tracing enrichment idempotently."""

        for label in ("Decision", "Evidence", "Comment", "Issue"):
            self._query(
                f"MATCH (node:{label} {{snapshot_id: $snapshot_id}}) DETACH DELETE node",
                {"snapshot_id": snapshot_id},
            )
        self._load_batches(
            people,
            """
            UNWIND $rows AS row
            MERGE (p:Person {id: row.id})
            SET p.provider = row.provider,
                p.login = row.login,
                p.display_name = row.display_name,
                p.identity_source = row.identity_source
            """,
        )
        self._load_batches(
            issues,
            """
            UNWIND $rows AS row
            MERGE (issue:Issue {id: row.id})
            SET issue.snapshot_id = row.snapshot_id,
                issue.number = row.number,
                issue.title = row.title,
                issue.state = row.state,
                issue.created_at = row.created_at,
                issue.updated_at = row.updated_at,
                issue.html_url = row.html_url,
                issue.source_url = row.source_url,
                issue.body_excerpt = row.body_excerpt,
                issue.content_hash = row.content_hash
            """,
        )
        self._load_batches(
            [{"snapshot_id": snapshot_id, "issue_id": row["id"]} for row in issues],
            """
            UNWIND $rows AS row
            MATCH (s:Snapshot {id: row.snapshot_id}), (issue:Issue {id: row.issue_id})
            MERGE (s)-[:CONTAINS_ISSUE {snapshot_id: row.snapshot_id}]->(issue)
            """,
        )
        self._load_batches(
            comments,
            """
            UNWIND $rows AS row
            MERGE (comment:Comment {id: row.id})
            SET comment.snapshot_id = row.snapshot_id,
                comment.source_type = row.source_type,
                comment.source_id = row.source_id,
                comment.number = row.number,
                comment.body_excerpt = row.body_excerpt,
                comment.content_hash = row.content_hash,
                comment.created_at = row.created_at,
                comment.updated_at = row.updated_at,
                comment.html_url = row.html_url,
                comment.source_url = row.source_url
            """,
        )
        self._load_batches(
            [row for row in comments if row.get("person_id")],
            """
            UNWIND $rows AS row
            MATCH (p:Person {id: row.person_id}), (comment:Comment {id: row.id})
            MERGE (p)-[:AUTHORED_COMMENT {snapshot_id: row.snapshot_id}]->(comment)
            """,
        )
        for source_type, label in (("issue", "Issue"), ("pull_request", "PullRequest")):
            self._load_batches(
                [row for row in comment_sources if row.get("source_type", source_type) == source_type],
                f"""
                UNWIND $rows AS row
                MATCH (comment:Comment {{id: row.comment_id}}), (source:{label} {{id: row.source_id}})
                MERGE (comment)-[:ON {{snapshot_id: row.snapshot_id}}]->(source)
                """,
            )
        self._load_batches(
            comment_files,
            """
            UNWIND $rows AS row
            MATCH (comment:Comment {id: row.comment_id}), (file:File {id: row.file_id})
            MERGE (comment)-[:MENTIONS {snapshot_id: row.snapshot_id}]->(file)
            """,
        )
        self._load_batches(
            evidences,
            """
            UNWIND $rows AS row
            MERGE (evidence:Evidence {id: row.id})
            SET evidence.snapshot_id = row.snapshot_id,
                evidence.excerpt = row.excerpt,
                evidence.source_type = row.source_type,
                evidence.source_id = row.source_id,
                evidence.source_url = row.source_url,
                evidence.confidence = row.confidence,
                evidence.content_hash = row.content_hash
            """,
        )
        self._load_batches(
            decisions,
            """
            UNWIND $rows AS row
            MERGE (decision:Decision {id: row.id})
            SET decision.snapshot_id = row.snapshot_id,
                decision.topic = row.topic,
                decision.source_title = row.source_title,
                decision.statement = row.statement,
                decision.status = row.status,
                decision.confidence = row.confidence,
                decision.extraction_method = row.extraction_method,
                decision.source_type = row.source_type,
                decision.source_id = row.source_id,
                decision.source_url = row.source_url,
                decision.created_at = row.created_at,
                decision.content_hash = row.content_hash
            """,
        )
        self._load_batches(
            [{"snapshot_id": snapshot_id, "decision_id": row["id"]} for row in decisions],
            """
            UNWIND $rows AS row
            MATCH (s:Snapshot {id: row.snapshot_id}), (decision:Decision {id: row.decision_id})
            MERGE (s)-[:CONTAINS_DECISION {snapshot_id: row.snapshot_id}]->(decision)
            """,
        )
        for source_type, label in (("issue", "Issue"), ("pull_request", "PullRequest")):
            self._load_batches(
                [row for row in decision_sources if row.get("source_type") == source_type],
                f"""
                UNWIND $rows AS row
                MATCH (decision:Decision {{id: row.decision_id}}), (source:{label} {{id: row.source_id}})
                MERGE (decision)-[:DECIDED_IN {{snapshot_id: row.snapshot_id}}]->(source)
                """,
            )
        self._load_batches(
            [row for row in decision_sources if row.get("source_type") == "comment"],
            """
            UNWIND $rows AS row
            MATCH (decision:Decision {id: row.decision_id}), (comment:Comment {id: row.source_id})
            MERGE (decision)-[:DECIDED_IN {snapshot_id: row.snapshot_id}]->(comment)
            """,
        )
        self._load_batches(
            decision_evidence,
            """
            UNWIND $rows AS row
            MATCH (decision:Decision {id: row.decision_id}), (evidence:Evidence {id: row.evidence_id})
            MERGE (decision)-[:SUPPORTED_BY {snapshot_id: row.snapshot_id}]->(evidence)
            """,
        )
        self._load_batches(
            supersession_refs,
            """
            UNWIND $rows AS row
            MATCH (decision:Decision {id: row.decision_id}),
                  (older:Decision {snapshot_id: row.snapshot_id, source_id: row.target_source_id})
            MERGE (decision)-[:SUPERSEDES {snapshot_id: row.snapshot_id}]->(older)
            """,
        )
        self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})
            SET s.decision_enriched_at = $enriched_at,
                s.issue_count = $issue_count,
                s.decision_comment_count = $comment_count,
                s.decision_count = $decision_count,
                s.decision_warnings = $warnings
            """,
            {
                "snapshot_id": snapshot_id,
                "enriched_at": enriched_at,
                "issue_count": len(issues),
                "comment_count": len(comments),
                "decision_count": len(decisions),
                "warnings": warnings[:100],
            },
        )

    def load(self, data: SnapshotData) -> dict[str, int]:
        """Write a snapshot and mark it complete only after all writes succeed."""

        snapshot_id = data.snapshot["id"]
        try:
            self._query(
                """
                MERGE (r:Repository {id: $id})
                SET r.full_name = $full_name,
                    r.name = $name,
                    r.description = $description,
                    r.default_branch = $default_branch,
                    r.html_url = $html_url,
                    r.provider = $provider,
                    r.source_type = $source_type,
                    r.source_url = $source_url,
                    r.observed_at = $observed_at
                """,
                data.repository,
            )
            self._query(
                """
                MERGE (s:Snapshot {id: $id})
                SET s.repository_id = $repository_id,
                    s.commit_sha = $commit_sha,
                    s.tree_sha = $tree_sha,
                    s.status = $status,
                    s.captured_at = $captured_at,
                    s.source_type = $source_type,
                    s.source_url = $source_url,
                    s.ingestion_version = $ingestion_version,
                    s.file_count = $file_count,
                    s.commit_count = $commit_count,
                    s.error = NULL
                """,
                data.snapshot,
            )
            self._query(
                """
                MATCH (r:Repository {id: $repository_id}), (s:Snapshot {id: $snapshot_id})
                MERGE (r)-[rel:HAS_SNAPSHOT]->(s)
                SET rel.observed_at = $captured_at
                """,
                {
                    "repository_id": data.repository["id"],
                    "snapshot_id": snapshot_id,
                    "captured_at": data.snapshot["captured_at"],
                },
            )

            self._load_batches(
                data.files,
                """
                UNWIND $rows AS row
                MERGE (f:File {id: row.id})
                SET f.repository_id = row.repository_id,
                    f.path = row.path,
                    f.extension = row.extension,
                    f.kind = row.kind,
                    f.source_url = row.source_url
                """,
            )
            self._load_batches(
                data.commits,
                """
                UNWIND $rows AS row
                MERGE (c:Commit {id: row.id})
                SET c.sha = row.sha,
                    c.message = row.message,
                    c.subject = row.subject,
                    c.authored_at = row.authored_at,
                    c.committed_at = row.committed_at,
                    c.html_url = row.html_url,
                    c.additions = row.additions,
                    c.deletions = row.deletions,
                    c.changed_files = row.changed_files,
                    c.partial = row.partial,
                    c.source_url = row.source_url
                """,
            )
            self._load_batches(
                data.people,
                """
                UNWIND $rows AS row
                MERGE (p:Person {id: row.id})
                SET p.provider = row.provider,
                    p.login = row.login,
                    p.display_name = row.display_name,
                    p.identity_source = row.identity_source
                """,
            )
            self._load_batches(
                data.snapshot_files,
                """
                UNWIND $rows AS row
                MATCH (s:Snapshot {id: row.snapshot_id}), (f:File {id: row.file_id})
                MERGE (s)-[rel:CONTAINS_FILE {snapshot_id: row.snapshot_id, file_id: row.file_id}]->(f)
                SET rel.file_sha = row.file_sha,
                    rel.size = row.size,
                    rel.mode = row.mode,
                    rel.source_url = row.source_url
                """,
            )
            self._load_batches(
                [
                    {"snapshot_id": snapshot_id, "commit_id": row["id"]}
                    for row in data.commits
                    if not row["partial"]
                ],
                """
                UNWIND $rows AS row
                MATCH (s:Snapshot {id: row.snapshot_id}), (c:Commit {id: row.commit_id})
                MERGE (s)-[rel:CONTAINS_COMMIT {snapshot_id: row.snapshot_id, commit_id: row.commit_id}]->(c)
                SET rel.source_type = 'github_rest'
                """,
            )
            self._load_batches(
                data.changed_files,
                """
                UNWIND $rows AS row
                MATCH (c:Commit {id: row.commit_id}), (f:File {id: row.file_id})
                MERGE (c)-[rel:CHANGED {snapshot_id: row.snapshot_id, file_id: row.file_id}]->(f)
                SET rel.status = row.status,
                    rel.additions = row.additions,
                    rel.deletions = row.deletions,
                    rel.previous_path = row.previous_path,
                    rel.patch = row.patch,
                    rel.patch_available = row.patch_available,
                    rel.patch_truncated = row.patch_truncated,
                    rel.patch_char_count = row.patch_char_count,
                    rel.source_url = row.source_url
                """,
            )
            for relationship_rows, relationship_type in (
                (data.authored_by, "AUTHORED_BY"),
                (data.committed_by, "COMMITTED_BY"),
            ):
                self._load_batches(
                    relationship_rows,
                    f"""
                    UNWIND $rows AS row
                    MATCH (c:Commit {{id: row.commit_id}}), (p:Person {{id: row.person_id}})
                    MERGE (c)-[rel:{relationship_type} {{snapshot_id: row.snapshot_id}}]->(p)
                    SET rel.source_type = 'github_rest'
                    """,
                )
            self._load_batches(
                data.parent_edges,
                """
                UNWIND $rows AS row
                MATCH (c:Commit {id: row.commit_id}), (p:Commit {id: row.parent_id})
                MERGE (c)-[rel:PARENT_OF {snapshot_id: row.snapshot_id}]->(p)
                SET rel.source_type = 'github_rest'
                """,
            )

            self._query(
                """
                MATCH (s:Snapshot {id: $snapshot_id})
                SET s.status = 'complete', s.error = NULL
                """,
                {"snapshot_id": snapshot_id},
            )
            return data.counts
        except Exception as exc:
            try:
                self._mark_status(snapshot_id, "failed", str(exc)[:2_000])
            except Exception:
                pass
            raise

