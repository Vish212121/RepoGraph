"""No-graph baseline used to quantify the value of RepoBrain context."""

from __future__ import annotations

import time

from app.agent.ollama import OllamaClient
from app.evaluation.models import EvaluationCase, EvaluationResult
from app.evaluation.scorer import contains_all


BASELINE_PROMPT = """Answer the user's repository question as a general language model.
Do not pretend to have access to a repository, graph, or source files. If the question
requires repository-specific facts that were not supplied, say that you cannot verify them.
"""


def score_baseline(case: EvaluationCase, ollama: OllamaClient) -> EvaluationResult:
    started = time.perf_counter()
    try:
        answer = ollama.generate(BASELINE_PROMPT, case.question)
    except Exception as exc:
        answer = f"Baseline unavailable: {exc}"
    elapsed = (time.perf_counter() - started) * 1000
    return EvaluationResult(
        case_id=case.case_id,
        system="baseline-no-graph",
        question=case.question,
        category=case.category,
        snapshot_id=case.snapshot_id,
        answer=answer,
        answer_match=contains_all(answer, case.expected_answer_facts),
        evidence_match=False,
        has_sources=False,
        expected_tool=case.expected_tool,
        actual_tool=None,
        execution_mode="baseline",
        latency_ms=round(elapsed, 2),
        tool_match=False,
        requires_relationship_proof=bool(case.minimum_hops or case.required_relationships),
        relationship_match=False,
        warning_match=True,
        graph_proof_match=False,
        details={
            "limitation": "no graph context supplied",
            "expected_answer_facts": list(case.expected_answer_facts),
            "expected_evidence_facts": list(case.expected_evidence_facts),
            "source_count": 0,
            "max_hops": 0,
            "relationships_seen": [],
        },
    )

