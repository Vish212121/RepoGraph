from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.models import EvaluationCase


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return ()
    return tuple(item.strip() for item in value)


def case_from_value(value: dict[str, object]) -> EvaluationCase:
    question = str(value["question"]).strip()
    answer_facts = _strings(value.get("expected_answer_facts", value.get("expected_contains", [])))
    evidence_facts = _strings(value.get("expected_evidence_facts", answer_facts))
    if not answer_facts:
        raise ValueError(f"{value.get('case_id', 'unknown')}: expected_answer_facts must not be empty")
    repeated = [fact for fact in answer_facts if fact.casefold() in question.casefold()]
    if repeated:
        raise ValueError(
            f"{value.get('case_id', 'unknown')}: expected answer facts must not be copied from the question: {repeated}"
        )
    return EvaluationCase(
        case_id=str(value["case_id"]),
        question=question,
        expected_answer_facts=answer_facts,
        expected_evidence_facts=evidence_facts,
        requires_graph=bool(value.get("requires_graph", True)),
        expected_tool=value.get("expected_tool") if isinstance(value.get("expected_tool"), str) else None,
        category=str(value.get("category", "repository")),
        snapshot_id=value.get("snapshot_id") if isinstance(value.get("snapshot_id"), str) else None,
        minimum_source_urls=max(0, int(value.get("minimum_source_urls", 1))),
        minimum_hops=max(0, int(value.get("minimum_hops", 0))),
        required_relationships=_strings(value.get("required_relationships", [])),
        expected_warnings=_strings(value.get("expected_warnings", [])),
    )


def load_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(case_from_value(json.loads(line)))
    return cases

