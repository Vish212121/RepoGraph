"""Enrich an existing complete snapshot with static Python dependency edges."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.graph.connection import get_graph
from app.ingestion.dependencies import extract_python_dependencies
from app.ingestion.github_client import GitHubClient
from app.ingestion.loader import GraphLoader


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DependencyEnricher:
    def __init__(
        self,
        graph: Any | None = None,
        client: GitHubClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.graph = graph or get_graph(self.settings)
        self.client = client or GitHubClient(
            self.settings.github_api_base_url,
            self.settings.github_token,
        )
        self.loader = GraphLoader(self.graph, self.settings.ingest_batch_size)

    def _query(self, query: str, params: dict[str, Any]) -> list[list[Any]]:
        response = self.graph.ro_query(query, params)
        return list(getattr(response, "result_set", []))

    def enrich(self, snapshot_id: str | None = None) -> dict[str, Any]:
        snapshot_rows = self._query(
            """
            MATCH (r:Repository)-[:HAS_SNAPSHOT]->(s:Snapshot)
            WHERE s.status = 'complete' AND ($snapshot_id IS NULL OR s.id = $snapshot_id)
            RETURN s.id, s.commit_sha, r.full_name
            ORDER BY s.captured_at DESC
            LIMIT 1
            """,
            {"snapshot_id": snapshot_id},
        )
        if not snapshot_rows:
            raise RuntimeError("No complete snapshot found for dependency enrichment")
        resolved_id, commit_sha, repository = map(str, snapshot_rows[0][:3])
        file_rows = self._query(
            """
            MATCH (s:Snapshot {id: $snapshot_id})-[:CONTAINS_FILE]->(f:File)
            RETURN f.id, f.path, f.source_url
            """,
            {"snapshot_id": resolved_id},
        )
        files = {str(row[1]): {"id": str(row[0]), "source_url": row[2]} for row in file_rows}
        python_paths = sorted(path for path in files if path.endswith(".py"))[: self.settings.dependency_max_files]
        edges: list[dict[str, Any]] = []
        warnings: list[str] = []
        for source_path in python_paths:
            try:
                source, payload = self.client.get_file_content(repository, source_path, commit_sha)
                if len(source.encode("utf-8")) > self.settings.dependency_content_max_bytes:
                    warnings.append(f"Skipped {source_path}: content exceeds configured size limit")
                    continue
                extracted = extract_python_dependencies(source_path, source, set(files))
                warnings.extend(extracted.warnings)
                for dependency in extracted.dependencies:
                    edges.append(
                        {
                            "snapshot_id": resolved_id,
                            "source_file_id": files[source_path]["id"],
                            "target_file_id": files[dependency.target_path]["id"],
                            "source_path": source_path,
                            "target_path": dependency.target_path,
                            "import_name": dependency.import_name,
                            "edge_type": dependency.edge_type,
                            "confidence": dependency.confidence,
                            "evidence_level": "static",
                            "source_url": files[source_path]["source_url"],
                            "content_sha": payload.get("sha"),
                            "extracted_at": _now(),
                        }
                    )

            except Exception as exc:
                warnings.append(f"Could not enrich {source_path}: {exc}")

        self.loader.load_dependencies(edges, resolved_id, _now(), warnings)
        return {
            "snapshot_id": resolved_id,
            "repository": repository,
            "files_scanned": len(python_paths),
            "dependency_edges": len(edges),
            "warnings": warnings[:100],
        }
