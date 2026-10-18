from types import SimpleNamespace

from app.agent.orchestrator import ReasoningAgent
from app.evidence.models import EvidenceBundle


class FakeTools:
    def file_history(self, path_fragment, snapshot_id=None):
        return EvidenceBundle(
            tool_name="file_history",
            query="MATCH ...",
            parameters={"path_fragment": path_fragment, "snapshot_id": snapshot_id},
            columns=["file_path", "commit_sha"],
            rows=[{"file_path": path_fragment, "commit_sha": "abc123"}],
            snapshot_id=snapshot_id or "snap-1",
            source_urls=["https://github.com/example/commit/abc123"],
        )


class FakeOllama:
    model = "test-model"

    def generate(self, system_prompt, user_prompt):
        assert "file_history" in user_prompt
        return "The graph tool file_history shows src/flask/app.py in snapshot snap-1."


def test_agent_returns_model_answer_with_evidence() -> None:
    response = ReasoningAgent(tools=FakeTools(), ollama_client=FakeOllama()).answer(
        "Show the history of src/flask/app.py", snapshot_id="snap-1"
    )

    assert response.intent == "file_history"
    assert response.answer == "The graph tool file_history shows src/flask/app.py in snapshot snap-1."
    assert response.evidence is not None
    assert response.evidence.rows[0]["commit_sha"] == "abc123"
    assert response.used_fallback is False


def test_agent_abstains_when_intent_is_not_supported() -> None:
    response = ReasoningAgent(tools=FakeTools(), ollama_client=FakeOllama()).answer(
        "Generate a pull request for this repository"
    )

    assert response.intent == "unsupported"
    assert response.evidence is None
    assert response.used_fallback is True
