"""Integration smoke tests for the local FalkorDB foundation."""

from uuid import uuid4

from app.config import get_settings
from app.graph.connection import get_graph


def test_graph_connection_and_temporary_node_lifecycle() -> None:
    settings = get_settings()
    graph = get_graph(settings)
    test_id = str(uuid4())

    try:
        created = graph.query(
            """
            CREATE (n:RepoBrainSmoke {test_id: $test_id, milestone: $milestone})
            RETURN n.test_id AS test_id, n.milestone AS milestone
            """,
            {"test_id": test_id, "milestone": "falkordb-foundation"},
        ).result_set

        assert created == [[test_id, "falkordb-foundation"]]

        read_back = graph.ro_query(
            """
            MATCH (n:RepoBrainSmoke {test_id: $test_id})
            RETURN n.test_id AS test_id, n.milestone AS milestone
            """,
            {"test_id": test_id},
        ).result_set

        assert read_back == [[test_id, "falkordb-foundation"]]
    finally:
        graph.query(
            "MATCH (n:RepoBrainSmoke {test_id: $test_id}) DELETE n",
            {"test_id": test_id},
        )

    remaining = graph.ro_query(
        "MATCH (n:RepoBrainSmoke {test_id: $test_id}) RETURN n.test_id",
        {"test_id": test_id},
    ).result_set

    assert remaining == []
