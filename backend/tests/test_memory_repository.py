from types import SimpleNamespace

import pytest

from app.embeddings.ollama import OllamaEmbeddingError
from app.memory.models import FindingCreate
from app.memory.repository import MemoryRepository
from app.tenant import resolve_demo_tenant


class FakeGraph:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def ro_query(self, query, parameters):
        self.queries.append((query, parameters))
        return SimpleNamespace(result_set=self.rows, header=[])


class SequencedGraph:
    def __init__(self, read_rows):
        self.read_rows = iter(read_rows)
        self.read_queries = []
        self.write_queries = []

    def ro_query(self, query, parameters):
        self.read_queries.append((query, parameters))
        return SimpleNamespace(result_set=next(self.read_rows), header=[])

    def query(self, query, parameters=None):
        self.write_queries.append((query, parameters or {}))
        return SimpleNamespace(result_set=[], header=[])


class FakeEmbeddingClient:
    model = "nomic-embed-text"

    def embed(self, value):
        return SimpleNamespace(vectors=[[0.11, 0.22, 0.33]])


class UnavailableEmbeddingClient:
    model = "nomic-embed-text"

    def embed(self, value):
        raise OllamaEmbeddingError("not running")


def test_recall_context_filters_by_internal_tenant_and_preserves_sources() -> None:
    graph = FakeGraph(
        [[
            "finding-1", "The app route finding", "active", 1, "snap-1",
            "2026-10-17T10:00:00Z", "2026-10-17T10:00:00Z",
            '[{"type":"file","value":"src/flask/app.py"}]',
            '["https://github.com/source"]', "session-1",
        ]]
    )

    evidence = MemoryRepository(graph).recall_context("tenant_demo_alpha", "app.py", "snap-1")

    assert evidence.rows[0]["finding_id"] == "finding-1"
    assert evidence.rows[0]["source_urls"] == ["https://github.com/source"]
    assert evidence.rows[0]["stale"] is False
    assert evidence.parameters["tenant_id"] == "tenant_demo_alpha"
    assert evidence.source_urls == ["https://github.com/source"]
    assert "f.tenant_id = $tenant_id" in graph.queries[0][0]


def test_demo_tenant_mapping_rejects_arbitrary_tenant_ids() -> None:
    assert resolve_demo_tenant("demo-alpha") == "tenant_demo_alpha"
    assert resolve_demo_tenant("demo-beta") == "tenant_demo_beta"
    with pytest.raises(ValueError):
        resolve_demo_tenant("tenant_someone_else")


def test_recall_context_uses_vector_candidates_then_tenant_filtered_graph_context() -> None:
    base_row = [
        "finding-1", "The Flask application entry point is app.py", "active", 1, "snap-1",
        "2026-10-17T10:00:00Z", "2026-10-17T10:00:00Z",
        '[{"type":"file","value":"src/flask/app.py"}]', '["https://github.com/source"]', "session-1",
    ]
    graph = SequencedGraph(
        [
            [],  # no memory index configuration exists yet
            [base_row + [0.91]],  # semantic vector candidates
            [],  # lexical fallback adds no duplicate
            [["finding-1", ["src/flask/app.py"]]],  # Finding-[:ABOUT]->File expansion
        ]
    )

    evidence = MemoryRepository(graph, embedding_client=FakeEmbeddingClient()).recall_context(
        "tenant_demo_alpha",
        "What did I learn about the application entry point?",
        "snap-1",
    )

    vector_query, vector_parameters = graph.read_queries[1]
    assert "db.idx.vector.queryNodes" in vector_query
    assert "node.tenant_id = $tenant_id" in vector_query
    assert vector_parameters["tenant_id"] == "tenant_demo_alpha"
    assert "CREATE VECTOR INDEX FOR (f:Finding) ON (f.embedding)" in graph.write_queries[0][0]
    assert evidence.rows[0]["retrieval_method"] == "semantic"
    assert evidence.rows[0]["semantic_score"] == 0.91
    assert evidence.rows[0]["linked_entities"] == ["src/flask/app.py"]
    assert "[redacted]" in evidence.query
    assert "0.11" not in evidence.query
    assert "embedding" not in evidence.parameters


def test_recall_context_keeps_lexical_fallback_when_embeddings_are_unavailable() -> None:
    graph = SequencedGraph(
        [
            [[
                "finding-1", "The app route finding", "active", 1, "snap-1",
                "2026-10-17T10:00:00Z", "2026-10-17T10:00:00Z",
                "[]", "[]", "session-1",
            ]],
            [["finding-1", []]],
        ]
    )

    evidence = MemoryRepository(graph, embedding_client=UnavailableEmbeddingClient()).recall_context(
        "tenant_demo_alpha", "app.py", "snap-1"
    )

    assert evidence.rows[0]["retrieval_method"] == "lexical fallback"
    assert any("Semantic retrieval is unavailable" in warning for warning in evidence.warnings)


def test_create_finding_persists_embedding_after_the_text_finding_is_saved() -> None:
    graph = SequencedGraph([[], []])

    finding = MemoryRepository(graph, embedding_client=FakeEmbeddingClient()).create_finding(
        "tenant_demo_alpha",
        FindingCreate(text="The application entry point is src/flask/app.py", idempotency_key="finding-1"),
    )

    assert finding["embedding_status"] == "ready"
    assert "CREATE (f:Finding" in graph.write_queries[0][0]
    assert "CREATE VECTOR INDEX FOR (f:Finding) ON (f.embedding)" in graph.write_queries[1][0]
    assert "f.embedding = vecf32" in graph.write_queries[3][0]
    assert all("embedding" not in parameters for _, parameters in graph.write_queries)
