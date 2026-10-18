from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_answer_facts: tuple[str, ...]
    expected_evidence_facts: tuple[str, ...] = ()
    requires_graph: bool = True
    expected_tool: str | None = None
    category: str = "repository"
    snapshot_id: str | None = None
    minimum_source_urls: int = 1
    minimum_hops: int = 0
    required_relationships: tuple[str, ...] = ()
    expected_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    system: str
    question: str
    category: str
    snapshot_id: str | None
    answer: str
    answer_match: bool
    evidence_match: bool
    has_sources: bool
    expected_tool: str | None
    actual_tool: str | None
    execution_mode: str | None
    latency_ms: float
    tool_match: bool = False
    requires_relationship_proof: bool = False
    relationship_match: bool = False
    warning_match: bool = True
    graph_proof_match: bool = False
    details: dict[str, Any] = field(default_factory=dict)

