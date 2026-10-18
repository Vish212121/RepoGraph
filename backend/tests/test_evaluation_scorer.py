import pytest

from app.agent.orchestrator import ReasoningAgent
from app.evaluation.baseline import score_baseline
from app.evaluation.fixtures import case_from_value
from app.evaluation.memory_contract import run_tenant_isolation_check
from app.evaluation.models import EvaluationCase
from app.evaluation.scorer import render_markdown, score_agent, summarize
from app.evidence.models import EvidenceBundle


class FakeTools:
    def file_history(self, **kwargs):
        return EvidenceBundle(
            tool_name="file_history",
            query="MATCH ...",
            parameters=kwargs,
            columns=["file_path", "contributor"],
            rows=[{"file_path": "src/flask/app.py", "contributor": "davidism"}],
            snapshot_id="snap-1",
            source_urls=["https://example.test/file"],
        )

    def impact_analysis(self, **kwargs):
        return EvidenceBundle(
            tool_name="impact_analysis",
            query="MATCH path",
            parameters=kwargs,
            columns=["affected_file", "hop_distance", "witness_path", "edge_types"],
            rows=[{
                "affected_file": "src/flask/cli.py",
                "hop_distance": 2,
                "witness_path": ["src/flask/cli.py", "src/flask/ctx.py", "src/flask/app.py"],
                "edge_types": ["python_import", "python_import"],
            }],
            snapshot_id="snap-1",
            source_urls=["https://example.test/file"],
            result_type="derived",
            warnings=["Dependency edges are statically extracted from Python imports."],
        )


class FakeOllama:
    model = "test-model"

    def generate(self, system_prompt, user_prompt):
        return "The graph shows davidism and src/flask/cli.py. Tool: file_history. Snapshot: snap-1."


class EchoBaseline:
    def generate(self, system_prompt, user_prompt):
        return user_prompt


def test_scorer_requires_distinct_facts_in_answer_evidence_and_sources():
    case = EvaluationCase(
        case_id="history",
        question="Show the history of src/flask/app.py",
        expected_answer_facts=("davidism",),
        expected_evidence_facts=("davidism",),
        expected_tool="file_history",
    )
    result = score_agent(case, ReasoningAgent(tools=FakeTools(), ollama_client=FakeOllama()), "test")

    assert result.answer_match is True
    assert result.evidence_match is True
    assert result.has_sources is True
    assert result.tool_match is True
    assert result.graph_proof_match is True
    assert summarize([result])["graph_proof_accuracy"] == 1.0


def test_scorer_requires_multi_hop_and_relationship_proof():
    case = EvaluationCase(
        case_id="impact",
        question="What files may be affected if src/flask/app.py changes?",
        expected_answer_facts=("src/flask/cli.py",),
        expected_evidence_facts=("src/flask/cli.py",),
        expected_tool="impact_analysis",
        minimum_hops=2,
        required_relationships=("python_import",),
        expected_warnings=("Dependency edges are statically extracted",),
    )
    result = score_agent(case, ReasoningAgent(tools=FakeTools(), ollama_client=FakeOllama()), "test")

    assert result.relationship_match is True
    assert result.details["max_hops"] == 2
    assert result.graph_proof_match is True


def test_baseline_that_only_echoes_the_question_cannot_pass_distinct_fact_check():
    case = EvaluationCase(
        case_id="contributors",
        question="Which contributors changed files matching app.py?",
        expected_answer_facts=("davidism",),
        expected_evidence_facts=("davidism",),
        expected_tool="file_contributors",
    )

    result = score_baseline(case, EchoBaseline())

    assert result.answer_match is False
    assert result.evidence_match is False
    assert result.graph_proof_match is False


def test_fixture_loader_rejects_expected_fact_copied_from_question():
    with pytest.raises(ValueError, match="copied from the question"):
        case_from_value({"case_id": "bad", "question": "Show app.py", "expected_answer_facts": ["app.py"]})


def test_markdown_report_shows_graph_proof_columns():
    case = EvaluationCase(
        case_id="history",
        question="Show the history of src/flask/app.py",
        expected_answer_facts=("davidism",),
        expected_evidence_facts=("davidism",),
        expected_tool="file_history",
    )
    result = score_agent(case, ReasoningAgent(tools=FakeTools(), ollama_client=FakeOllama()), "repobrain")
    markdown = render_markdown([result], {"repobrain": summarize([result])})

    assert "Graph proof" in markdown
    assert "history" in markdown


class FakeMemoryGraph:
    def __init__(self):
        self.deleted = []

    def query(self, query, parameters):
        self.deleted.append((query, parameters))


class FakeMemoryRepository:
    def __init__(self, leak_to_beta: bool = False):
        self.graph = FakeMemoryGraph()
        self.leak_to_beta = leak_to_beta
        self.finding_id = "evaluation-finding"

    def create_finding(self, tenant_id, payload):
        assert tenant_id == "tenant_demo_alpha"
        return {"finding_id": self.finding_id}

    def recall_context(self, tenant_id, query, limit):
        rows = [{"finding_id": self.finding_id}] if tenant_id == "tenant_demo_alpha" or self.leak_to_beta else []
        return EvidenceBundle(
            tool_name="recall_context",
            query="MATCH finding",
            parameters={},
            columns=["finding_id"],
            rows=rows,
            snapshot_id=None,
        )


def test_tenant_memory_contract_requires_alpha_visibility_beta_absence_and_cleanup():
    repository = FakeMemoryRepository()

    result = run_tenant_isolation_check(repository=repository)

    assert result.passed is True
    assert result.alpha_can_recall is True
    assert result.beta_can_recall is False
    assert result.cleaned_up is True
    assert "DETACH DELETE" in repository.graph.deleted[0][0]


def test_tenant_memory_contract_detects_a_leak():
    result = run_tenant_isolation_check(repository=FakeMemoryRepository(leak_to_beta=True))

    assert result.passed is False
    assert result.beta_can_recall is True
