"""Tenant-filtered, idempotent memory operations backed by FalkorDB."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings, get_settings
from app.embeddings.ollama import OllamaEmbeddingClient
from app.evidence.models import EvidenceBundle
from app.memory.models import FindingCreate, FindingUpdate, finding_row


_FINDING_COLUMNS = (
    "finding_id", "text", "status", "version", "snapshot_id", "created_at", "updated_at",
    "references_json", "source_urls_json", "session_id",
)
_VECTOR_INDEX_CONFIG_ID = "finding_embedding"
_VECTOR_INDEX_LABEL = "Finding"
_VECTOR_INDEX_PROPERTY = "embedding"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _terms(value: str) -> list[str]:
    return sorted({term for term in re.findall(r"[a-z0-9_./-]+", value.casefold()) if len(term) >= 3})[:20]


class MemoryRepository:
    """The only component allowed to read or write user-owned graph nodes."""

    def __init__(
        self,
        graph: Any,
        settings: Settings | None = None,
        embedding_client: Any | None = None,
    ) -> None:
        self.graph = graph
        self.settings = settings or get_settings()
        self.embedding_client = embedding_client or OllamaEmbeddingClient(
            self.settings.ollama_base_url,
            self.settings.ollama_embedding_model,
            self.settings.embedding_timeout_seconds,
        )

    def _query(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return self.graph.query(query, params or {})

    def _read(self, query: str, params: dict[str, Any]) -> list[list[Any]]:
        response = self.graph.ro_query(query, params)
        return list(getattr(response, "result_set", []))

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def ensure_session(self, tenant_id: str, session_id: str | None = None) -> str:
        requested = session_id or str(uuid4())
        if session_id:
            existing = self._read(
                """
                MATCH (s:Session {id: $session_id, tenant_id: $tenant_id})
                RETURN s.id
                LIMIT 1
                """,
                {"session_id": requested, "tenant_id": tenant_id},
            )
            if existing:
                self._query(
                    "MATCH (s:Session {id: $session_id, tenant_id: $tenant_id}) SET s.updated_at = $updated_at",
                    {"session_id": requested, "tenant_id": tenant_id, "updated_at": _now()},
                )
                return requested
            requested = str(uuid4())
        self._query(
            """
            MERGE (s:Session {id: $session_id})
            SET s.tenant_id = $tenant_id,
                s.created_at = coalesce(s.created_at, $created_at),
                s.updated_at = $created_at
            """,
            {"session_id": requested, "tenant_id": tenant_id, "created_at": _now()},
        )
        return requested

    def record_interaction(
        self,
        tenant_id: str,
        session_id: str,
        question: str,
        snapshot_id: str | None,
        response: Any,
    ) -> str:
        question_id = str(uuid4())
        created_at = _now()
        self._query(
            """
            CREATE (q:Question {
                id: $question_id,
                tenant_id: $tenant_id,
                session_id: $session_id,
                text: $text,
                answer: $answer,
                intent: $intent,
                snapshot_id: $snapshot_id,
                created_at: $created_at
            })
            WITH q
            MATCH (s:Session {id: $session_id, tenant_id: $tenant_id})
            MERGE (s)-[:HAS_QUESTION {tenant_id: $tenant_id}]->(q)
            """,
            {
                "question_id": question_id,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "text": question,
                "answer": response.answer,
                "intent": response.intent,
                "snapshot_id": snapshot_id,
                "created_at": created_at,
            },
        )
        for index, call in enumerate(response.tool_calls):
            tool_call_id = f"{question_id}:tool:{index}"
            self._query(
                """
                MATCH (q:Question {id: $question_id, tenant_id: $tenant_id})
                CREATE (call:ToolCall {
                    id: $tool_call_id,
                    tenant_id: $tenant_id,
                    tool_name: $tool_name,
                    execution_mode: $execution_mode,
                    arguments_json: $arguments_json,
                    result_rows: $result_rows,
                    created_at: $created_at
                })
                MERGE (q)-[:USED_TOOL {tenant_id: $tenant_id}]->(call)
                """,
                {
                    "question_id": question_id,
                    "tenant_id": tenant_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": call.tool_name,
                    "execution_mode": call.execution_mode,
                    "arguments_json": json.dumps(call.arguments, default=str),
                    "result_rows": call.result_rows,
                    "created_at": created_at,
                },
            )
        evidence = response.evidence
        if evidence is not None:
            evidence_id = f"{question_id}:evidence"
            self._query(
                """
                MATCH (q:Question {id: $question_id, tenant_id: $tenant_id})
                CREATE (e:MemoryEvidence {
                    id: $evidence_id,
                    tenant_id: $tenant_id,
                    snapshot_id: $snapshot_id,
                    tool_name: $tool_name,
                    evidence_json: $evidence_json,
                    source_urls_json: $source_urls_json,
                    created_at: $created_at
                })
                MERGE (q)-[:RETURNED {tenant_id: $tenant_id}]->(e)
                """,
                {
                    "question_id": question_id,
                    "tenant_id": tenant_id,
                    "evidence_id": evidence_id,
                    "snapshot_id": evidence.snapshot_id,
                    "tool_name": evidence.tool_name,
                    "evidence_json": json.dumps(evidence.to_dict(), default=str),
                    "source_urls_json": json.dumps(evidence.source_urls),
                    "created_at": created_at,
                },
            )
        self._query(
            "MATCH (s:Session {id: $session_id, tenant_id: $tenant_id}) SET s.updated_at = $updated_at",
            {"session_id": session_id, "tenant_id": tenant_id, "updated_at": created_at},
        )
        return question_id

    def _finding_from_row(self, row: list[Any]) -> dict[str, Any]:
        value = dict(zip(_FINDING_COLUMNS, row, strict=False))
        value["references"] = self._json(value.pop("references_json", None), [])
        value["source_urls"] = self._json(value.pop("source_urls_json", None), [])
        return finding_row(value)

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        """Create a safe Cypher literal after the embedding client has validated every value."""

        if not vector or len(vector) > 4_096:
            raise ValueError("embedding dimension must be between 1 and 4096")
        return "[" + ",".join(repr(value) for value in vector) + "]"

    def _embedding_model(self) -> str:
        model = getattr(self.embedding_client, "model", self.settings.ollama_embedding_model)
        if not isinstance(model, str) or not model.strip():
            raise ValueError("embedding client must expose a non-empty model name")
        return model.strip()

    def _index_config(self) -> list[Any] | None:
        rows = self._read(
            """
            MATCH (config:MemoryIndexConfig {id: $id})
            RETURN config.embedding_model, config.embedding_dimensions, config.similarity_function
            LIMIT 1
            """,
            {"id": _VECTOR_INDEX_CONFIG_ID},
        )
        return rows[0] if rows else None

    def _ensure_vector_index(self, model: str, dimensions: int) -> None:
        """Provision one explicit index configuration and reject incompatible model changes."""

        if not 1 <= dimensions <= 4_096:
            raise ValueError("embedding dimension must be between 1 and 4096")

        config = self._index_config()
        if config:
            existing_model, existing_dimensions, similarity_function = config
            if int(existing_dimensions) != dimensions or similarity_function != "cosine":
                raise ValueError(
                    "memory embedding dimension or similarity changed; rebuild the FalkorDB vector index before continuing"
                )
            if existing_model != model:
                # A same-dimension model change is safe only after the backfill replaces
                # old vectors. The model predicate keeps mixed-model candidates hidden.
                self._query(
                    """
                    MATCH (config:MemoryIndexConfig {id: $id})
                    SET config.embedding_model = $model,
                        config.updated_at = $updated_at
                    """,
                    {"id": _VECTOR_INDEX_CONFIG_ID, "model": model, "updated_at": _now()},
                )
            return

        create_index = (
            "CREATE VECTOR INDEX FOR (f:Finding) ON (f.embedding) "
            f"OPTIONS {{dimension:{dimensions}, similarityFunction:'cosine'}}"
        )
        try:
            self._query(create_index)
        except Exception as exc:  # FalkorDB uses implementation-specific duplicate-index exceptions.
            if "exist" not in str(exc).casefold():
                raise RuntimeError("FalkorDB could not create the Finding embedding index") from exc

        self._query(
            """
            MERGE (config:MemoryIndexConfig {id: $id})
            SET config.embedding_model = $model,
                config.embedding_dimensions = $dimensions,
                config.similarity_function = 'cosine',
                config.updated_at = $updated_at
            """,
            {
                "id": _VECTOR_INDEX_CONFIG_ID,
                "model": model,
                "dimensions": dimensions,
                "updated_at": _now(),
            },
        )

    def _mark_embedding_unavailable(self, tenant_id: str, finding_id: str, reason: str) -> None:
        self._query(
            """
            MATCH (f:Finding {id: $finding_id, tenant_id: $tenant_id})
            SET f.embedding_status = 'unavailable',
                f.embedding_failure_reason = $reason,
                f.embedding_updated_at = $updated_at
            """,
            {
                "finding_id": finding_id,
                "tenant_id": tenant_id,
                "reason": reason,
                "updated_at": _now(),
            },
        )

    def _store_embedding(self, tenant_id: str, finding_id: str, text: str) -> None:
        result = self.embedding_client.embed(text)
        vector = result.vectors[0]
        model = self._embedding_model()
        self._ensure_vector_index(model, len(vector))
        vector_literal = self._vector_literal(vector)
        self._query(
            f"""
            MATCH (f:Finding {{id: $finding_id, tenant_id: $tenant_id}})
            SET f.embedding = vecf32({vector_literal}),
                f.embedding_status = 'ready',
                f.embedding_model = $model,
                f.embedding_dimensions = $dimensions,
                f.embedding_failure_reason = null,
                f.embedding_updated_at = $updated_at
            """,
            {
                "finding_id": finding_id,
                "tenant_id": tenant_id,
                "model": model,
                "dimensions": len(vector),
                "updated_at": _now(),
            },
        )

    def _store_embedding_or_mark_unavailable(self, tenant_id: str, finding_id: str, text: str) -> str:
        try:
            self._store_embedding(tenant_id, finding_id, text)
            return "ready"
        except Exception:
            # This is an optional enrichment boundary. A finding remains useful as lexical
            # memory when Ollama or the FalkorDB vector capability is unavailable.
            self._mark_embedding_unavailable(tenant_id, finding_id, "semantic_embedding_unavailable")
            return "unavailable"

    def create_finding(self, tenant_id: str, payload: FindingCreate) -> dict[str, Any]:
        idempotency_key = payload.idempotency_key or str(uuid4())
        existing = self._read(
            """
            MATCH (f:Finding {tenant_id: $tenant_id, idempotency_key: $idempotency_key})
            RETURN f.id, f.text, f.status, f.version, f.snapshot_id, f.created_at, f.updated_at,
                   f.references_json, f.source_urls_json, f.session_id
            LIMIT 1
            """,
            {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
        )
        if existing:
            return self._finding_from_row(existing[0])
        finding_id = str(uuid4())
        created_at = _now()
        references = [reference.model_dump() for reference in payload.references]
        self._query(
            """
            CREATE (f:Finding {
                id: $finding_id,
                tenant_id: $tenant_id,
                text: $text,
                status: 'active',
                version: 1,
                snapshot_id: $snapshot_id,
                idempotency_key: $idempotency_key,
                references_json: $references_json,
                source_urls_json: $source_urls_json,
                session_id: $session_id,
                embedding_status: 'pending',
                created_at: $created_at,
                updated_at: $created_at
            })
            """,
            {
                "finding_id": finding_id,
                "tenant_id": tenant_id,
                "text": payload.text.strip(),
                "snapshot_id": payload.snapshot_id,
                "idempotency_key": idempotency_key,
                "references_json": json.dumps(references),
                "source_urls_json": json.dumps(sorted(set(payload.source_urls))),
                "session_id": payload.session_id,
                "created_at": created_at,
            },
        )
        self._link_references(tenant_id, finding_id, references, payload.snapshot_id)
        embedding_status = self._store_embedding_or_mark_unavailable(
            tenant_id,
            finding_id,
            payload.text.strip(),
        )
        return {
            "finding_id": finding_id,
            "text": payload.text.strip(),
            "status": "active",
            "version": 1,
            "snapshot_id": payload.snapshot_id,
            "created_at": created_at,
            "updated_at": created_at,
            "references": references,
            "source_urls": sorted(set(payload.source_urls)),
            "session_id": payload.session_id,
            "embedding_status": embedding_status,
        }

    def _link_references(
        self,
        tenant_id: str,
        finding_id: str,
        references: list[dict[str, Any]],
        snapshot_id: str | None,
    ) -> None:
        for reference_type, label, property_name in (
            ("file", "File", "path"),
            ("person", "Person", "login"),
            ("decision", "Decision", "id"),
            ("pull_request", "PullRequest", "id"),
            ("issue", "Issue", "id"),
        ):
            rows = [
                {"finding_id": finding_id, "tenant_id": tenant_id, "value": item["value"], "snapshot_id": snapshot_id}
                for item in references
                if item.get("type") == reference_type
            ]
            if not rows:
                continue
            self._query(
                f"""
                UNWIND $rows AS row
                MATCH (f:Finding {{id: row.finding_id, tenant_id: row.tenant_id}}),
                      (entity:{label} {{{property_name}: row.value}})
                MERGE (f)-[:ABOUT {{tenant_id: row.tenant_id, snapshot_id: row.snapshot_id}}]->(entity)
                """,
                {"rows": rows},
            )

    def recall_context(
        self,
        tenant_id: str,
        query_text: str,
        snapshot_id: str | None = None,
        limit: int = 10,
    ) -> EvidenceBundle:
        query_text = query_text.strip()
        if not query_text:
            raise ValueError("query must not be empty")
        limit = max(1, min(limit, 100))
        lexical_query = """
        MATCH (f:Finding)
        WHERE f.tenant_id = $tenant_id
          AND f.status <> 'archived'
          AND ANY(term IN $terms WHERE toLower(f.text) CONTAINS term OR toLower(f.references_json) CONTAINS term)
        RETURN f.id AS finding_id,
               f.text AS text,
               f.status AS status,
               f.version AS version,
               f.snapshot_id AS snapshot_id,
               f.created_at AS created_at,
               f.updated_at AS updated_at,
               f.references_json AS references_json,
               f.source_urls_json AS source_urls_json,
               f.session_id AS session_id
        ORDER BY f.updated_at DESC
        LIMIT $limit
        """
        lexical_parameters = {
            "tenant_id": tenant_id,
            "query": query_text,
            "terms": _terms(query_text) or [query_text.casefold()],
            "snapshot_id": snapshot_id,
            "limit": limit,
        }
        warnings = ["Memory results are user-owned findings, not current repository facts."]
        semantic_rows: list[dict[str, Any]] = []
        semantic_available = True
        candidate_limit = min(
            max(limit, limit * self.settings.memory_vector_candidate_multiplier),
            self.settings.memory_vector_max_candidates,
        )
        try:
            embedded_query = self.embedding_client.embed(query_text).vectors[0]
            embedding_model = self._embedding_model()
            self._ensure_vector_index(embedding_model, len(embedded_query))
            vector_literal = self._vector_literal(embedded_query)
            semantic_query = f"""
            CALL db.idx.vector.queryNodes(
                '{_VECTOR_INDEX_LABEL}',
                '{_VECTOR_INDEX_PROPERTY}',
                {candidate_limit},
                vecf32({vector_literal})
            ) YIELD node, score
            WITH node, score
            WHERE node.tenant_id = $tenant_id
              AND node.status <> 'archived'
              AND node.embedding_status = 'ready'
              AND node.embedding_model = $embedding_model
              AND score >= $minimum_score
            RETURN node.id AS finding_id,
                   node.text AS text,
                   node.status AS status,
                   node.version AS version,
                   node.snapshot_id AS snapshot_id,
                   node.created_at AS created_at,
                   node.updated_at AS updated_at,
                   node.references_json AS references_json,
                   node.source_urls_json AS source_urls_json,
                   node.session_id AS session_id,
                   score AS semantic_score
            ORDER BY semantic_score DESC, updated_at DESC
            LIMIT $limit
            """
            raw_semantic_rows = self._read(
                semantic_query,
                {
                    "tenant_id": tenant_id,
                    "embedding_model": embedding_model,
                    "minimum_score": self.settings.memory_vector_min_score,
                    "limit": limit,
                },
            )
            for raw_row in raw_semantic_rows:
                row = self._finding_from_row(raw_row[:len(_FINDING_COLUMNS)])
                row["semantic_score"] = round(float(raw_row[len(_FINDING_COLUMNS)]), 4)
                row["retrieval_method"] = "semantic"
                semantic_rows.append(row)
        except Exception:
            # Vector search is optional; preserve a bounded lexical path instead of turning
            # a missing Ollama model or unavailable vector index into a failed memory query.
            semantic_available = False
            warnings.append("Semantic retrieval is unavailable; showing lexical matches only.")

        lexical_rows = [self._finding_from_row(row) for row in self._read(lexical_query, lexical_parameters)]
        rows_by_id = {str(row["finding_id"]): row for row in semantic_rows}
        semantic_ids = list(rows_by_id)
        for row in lexical_rows:
            finding_id = str(row["finding_id"])
            existing = rows_by_id.get(finding_id)
            if existing is not None:
                existing["retrieval_method"] = "semantic + lexical"
                existing["lexical_match"] = True
            else:
                row["retrieval_method"] = "lexical fallback"
                row["lexical_match"] = True
                rows_by_id[finding_id] = row

        ordered_ids = semantic_ids + [
            str(row["finding_id"])
            for row in lexical_rows
            if str(row["finding_id"]) not in semantic_ids
        ]
        rows = [rows_by_id[finding_id] for finding_id in ordered_ids[:limit]]
        if semantic_available and not semantic_rows and lexical_rows:
            warnings.append("No semantic match met the relevance threshold; lexical matches are shown as a fallback.")

        self._attach_linked_entities(tenant_id, rows)
        for row in rows:
            row["stale"] = bool(snapshot_id and row.get("snapshot_id") not in (None, snapshot_id))
        source_urls = sorted({url for row in rows for url in row.get("source_urls", [])})
        if semantic_rows:
            warnings.append(
                "Semantic matches were ranked by FalkorDB's Finding embedding index, then tenant-filtered and expanded through ABOUT relationships."
            )
        if any(row.get("stale") for row in rows):
            warnings.append("Some recalled findings come from a different repository snapshot and may be stale.")
        return EvidenceBundle(
            tool_name="recall_context",
            query="""
            CALL db.idx.vector.queryNodes('Finding', 'embedding', $candidate_limit, vecf32([redacted]))
            YIELD node, score
            WITH node, score
            WHERE node.tenant_id = $tenant_id AND node.status <> 'archived'
            // Results are then augmented with lexical fallback and Finding-[:ABOUT]->entity graph context.
            """.strip(),
            parameters={
                "tenant_id": tenant_id,
                "query": query_text,
                "candidate_limit": candidate_limit,
                "minimum_score": self.settings.memory_vector_min_score,
                "lexical_terms": lexical_parameters["terms"],
                "snapshot_id": snapshot_id,
                "limit": limit,
            },
            columns=[
                "finding_id", "text", "status", "version", "snapshot_id", "created_at", "updated_at",
                "references", "source_urls", "session_id", "semantic_score", "retrieval_method",
                "lexical_match", "linked_entities", "stale",
            ],
            rows=rows,
            snapshot_id=snapshot_id,
            source_urls=source_urls,
            result_type="memory",
            warnings=warnings,
        )

    def _attach_linked_entities(self, tenant_id: str, rows: list[dict[str, Any]]) -> None:
        """Expand selected candidates through explicit Finding-to-repository relationships."""

        finding_ids = [str(row["finding_id"]) for row in rows if row.get("finding_id")]
        if not finding_ids:
            return
        linked_rows = self._read(
            """
            MATCH (f:Finding {tenant_id: $tenant_id})
            WHERE f.id IN $finding_ids
            OPTIONAL MATCH (f)-[:ABOUT]->(entity)
            RETURN f.id AS finding_id,
                   collect(DISTINCT coalesce(entity.path, entity.login, entity.id)) AS linked_entities
            """,
            {"tenant_id": tenant_id, "finding_ids": finding_ids},
        )
        by_id = {
            str(row[0]): [str(value) for value in (row[1] or []) if value is not None]
            for row in linked_rows
        }
        for row in rows:
            row["linked_entities"] = by_id.get(str(row["finding_id"]), [])

    def backfill_embeddings(self, tenant_id: str, limit: int = 100) -> dict[str, int]:
        """Generate vectors for legacy findings without re-writing their user-visible content."""

        limit = max(1, min(limit, 1_000))
        candidates = self._read(
            """
            MATCH (f:Finding {tenant_id: $tenant_id})
            WHERE f.status <> 'archived'
              AND (f.embedding_status IS NULL OR f.embedding_status <> 'ready' OR f.embedding_model <> $embedding_model)
            RETURN f.id, f.text
            ORDER BY f.updated_at DESC
            LIMIT $limit
            """,
            {"tenant_id": tenant_id, "embedding_model": self._embedding_model(), "limit": limit},
        )
        ready = 0
        unavailable = 0
        for finding_id, text in candidates:
            status = self._store_embedding_or_mark_unavailable(tenant_id, str(finding_id), str(text))
            if status == "ready":
                ready += 1
            else:
                unavailable += 1
        return {"examined": len(candidates), "embedded": ready, "unavailable": unavailable}

    def update_finding(self, tenant_id: str, finding_id: str, payload: FindingUpdate) -> dict[str, Any]:
        current = self._read(
            """
            MATCH (f:Finding {id: $finding_id, tenant_id: $tenant_id})
            RETURN f.id, f.text, f.status, f.version, f.snapshot_id, f.created_at, f.updated_at,
                   f.references_json, f.source_urls_json, f.session_id
            LIMIT 1
            """,
            {"finding_id": finding_id, "tenant_id": tenant_id},
        )
        if not current:
            raise KeyError("finding not found")
        before = self._finding_from_row(current[0])
        if before["version"] != payload.expected_version:
            raise ValueError(f"finding version conflict: expected {payload.expected_version}, current {before['version']}")
        updated_at = _now()
        self._query(
            """
            MATCH (f:Finding {id: $finding_id, tenant_id: $tenant_id, version: $expected_version})
            SET f.text = coalesce($text, f.text),
                f.status = coalesce($status, f.status),
                f.version = f.version + 1,
                f.updated_at = $updated_at
            """,
            {
                "finding_id": finding_id,
                "tenant_id": tenant_id,
                "expected_version": payload.expected_version,
                "text": payload.text,
                "status": payload.status,
                "updated_at": updated_at,
            },
        )
        if payload.text is not None and (payload.status or before["status"]) != "archived":
            self._store_embedding_or_mark_unavailable(tenant_id, finding_id, payload.text)
        after = dict(before)
        after.update({"text": payload.text or before["text"], "status": payload.status or before["status"], "version": payload.expected_version + 1, "updated_at": updated_at})
        return after
