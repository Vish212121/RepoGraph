import pytest
from pydantic import ValidationError

from app.api.dependencies import get_agent_or_503
from app.api.models import QueryRequest
from app.api.routes import app, health, query, snapshots
from app.evidence.models import EvidenceBundle
from app.mcp.contracts import ToolCallTrace


class FakeTools:
    def list_snapshots(self):
        return EvidenceBundle(
            tool_name="list_snapshots",
            query="MATCH snapshots",
            parameters={"limit": 20},
            columns=["snapshot_id", "repository"],
            rows=[{"snapshot_id": "snap-1", "repository": "pallets/flask"}],
            snapshot_id=None,
        )


class FakeAgent:
    tools = FakeTools()

    def answer(self, question, snapshot_id=None, tenant_id=None):
        from app.agent.orchestrator import AgentResponse

        return AgentResponse(
            question=question,
            intent="snapshot_overview",
            answer="The repository snapshot is available.",
            evidence=EvidenceBundle(
                tool_name="snapshot_overview",
                query="MATCH snapshot",
                parameters={"snapshot_id": snapshot_id},
                columns=["snapshot_id"],
                rows=[{"snapshot_id": snapshot_id or "snap-1"}],
                snapshot_id=snapshot_id or "snap-1",
                source_urls=["https://github.com/pallets/flask"],
            ),
            model="test-model",
            used_fallback=False,
            execution_mode="direct",
            tool_calls=(
                ToolCallTrace(
                    execution_mode="direct",
                    tool_name="snapshot_overview",
                    arguments={"snapshot_id": snapshot_id},
                    result_rows=1,
                ),
            ),
        )


app.dependency_overrides[get_agent_or_503] = lambda: FakeAgent()


def teardown_module() -> None:
    app.dependency_overrides.clear()


def test_health_endpoint() -> None:
    response = health()
    assert response.service == "repobrain-api"
    assert response.status == "ok"


def test_query_endpoint_returns_structured_evidence() -> None:
    response = query(QueryRequest(question="Give me an overview"), FakeAgent())
    assert response.intent == "snapshot_overview"
    assert response.evidence is not None
    assert response.evidence.tool_name == "snapshot_overview"
    assert response.evidence.source_urls == ["https://github.com/pallets/flask"]
    assert response.tool_calls == [
        {
            "execution_mode": "direct",
            "tool_name": "snapshot_overview",
            "arguments": {"snapshot_id": None},
            "result_rows": 1,
        }
    ]


def test_query_endpoint_rejects_blank_questions() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="  ")


def test_snapshots_endpoint_returns_snapshot_rows() -> None:
    response = snapshots(FakeAgent())
    assert len(response) == 1
    assert response[0].snapshot_id == "snap-1"
    assert response[0].repository == "pallets/flask"
