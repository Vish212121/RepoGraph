"""Deterministic scoring for evidence-backed repository evaluation cases."""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from statistics import median
from typing import Any, Iterable

from app.agent.orchestrator import AgentResponse, ReasoningAgent
from app.evaluation.models import EvaluationCase, EvaluationResult


def contains_all(text: str, expected: Iterable[str]) -> bool:
    """Use only fixture facts that are absent from the prompt itself."""

    lowered = text.casefold()
    return all(item.casefold() in lowered for item in expected)


def _evidence_text(response: AgentResponse) -> str:
    return json.dumps(response.evidence.to_dict(), default=str) if response.evidence else ""


def _relationship_match(case: EvaluationCase, response: AgentResponse) -> tuple[bool, dict[str, Any]]:
    evidence = response.evidence
    if evidence is None:
        return False, {"max_hops": 0, "relationships_seen": []}

    max_hops = 0
    relationships: set[str] = set()
    for row in [*evidence.rows, *evidence.derived_results]:
        hop_distance = row.get("hop_distance")
        if isinstance(hop_distance, (int, float)):
            max_hops = max(max_hops, int(hop_distance))
        witness_path = row.get("witness_path")
        if isinstance(witness_path, list):
            max_hops = max(max_hops, max(0, len(witness_path) - 1))
        edge_types = row.get("edge_types")
        if isinstance(edge_types, list):
            relationships.update(str(value) for value in edge_types if value)

    relation_text = _evidence_text(response).casefold()
    required_present = all(value.casefold() in relation_text for value in case.required_relationships)
    hops_present = max_hops >= case.minimum_hops
    return hops_present and required_present, {
        "max_hops": max_hops,
        "relationships_seen": sorted(relationships),
        "required_relationships": list(case.required_relationships),
    }


def score_agent(case: EvaluationCase, agent: ReasoningAgent, system: str) -> EvaluationResult:
    started = time.perf_counter()
    response: AgentResponse = agent.answer(case.question, snapshot_id=case.snapshot_id)
    elapsed = (time.perf_counter() - started) * 1000
    evidence = response.evidence
    evidence_text = _evidence_text(response)
    actual_tool = evidence.tool_name if evidence else None
    tool_match = case.expected_tool is None or case.expected_tool == actual_tool
    answer_match = contains_all(response.answer, case.expected_answer_facts)
    evidence_match = bool(evidence) and contains_all(evidence_text, case.expected_evidence_facts)
    source_count = len(evidence.source_urls) if evidence else 0
    has_sources = source_count >= case.minimum_source_urls
    relationship_match, relationship_details = _relationship_match(case, response)
    requires_relationship_proof = bool(case.minimum_hops or case.required_relationships)
    warning_text = "\n".join(evidence.warnings if evidence else [])
    warning_match = contains_all(warning_text, case.expected_warnings)
    graph_proof_match = (
        tool_match
        and evidence_match
        and has_sources
        and warning_match
        and (not case.requires_graph or relationship_match)
    )
    return EvaluationResult(
        case_id=case.case_id,
        system=system,
        question=case.question,
        category=case.category,
        snapshot_id=case.snapshot_id or (evidence.snapshot_id if evidence else None),
        answer=response.answer,
        answer_match=answer_match,
        evidence_match=evidence_match,
        has_sources=has_sources,
        expected_tool=case.expected_tool,
        actual_tool=actual_tool,
        execution_mode=response.execution_mode,
        latency_ms=round(elapsed, 2),
        tool_match=tool_match,
        requires_relationship_proof=requires_relationship_proof,
        relationship_match=relationship_match,
        warning_match=warning_match,
        graph_proof_match=graph_proof_match,
        details={
            "source_count": source_count,
            "expected_answer_facts": list(case.expected_answer_facts),
            "expected_evidence_facts": list(case.expected_evidence_facts),
            **relationship_details,
        },
    )


def _rate(results: list[EvaluationResult], attribute: str) -> float:
    return round(sum(bool(getattr(item, attribute)) for item in results) / len(results), 3) if results else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[rank], 2)


def summarize(results: list[EvaluationResult]) -> dict[str, Any]:
    if not results:
        return {
            "cases": 0,
            "answer_fact_accuracy": 0.0,
            "evidence_fact_accuracy": 0.0,
            "source_coverage": 0.0,
            "tool_selection_accuracy": 0.0,
            "relationship_proof_coverage": 0.0,
            "graph_proof_accuracy": 0.0,
            "average_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }
    latencies = [item.latency_ms for item in results]
    return {
        "cases": len(results),
        "answer_fact_accuracy": _rate(results, "answer_match"),
        "evidence_fact_accuracy": _rate(results, "evidence_match"),
        "source_coverage": _rate(results, "has_sources"),
        "tool_selection_accuracy": _rate(results, "tool_match"),
        "relationship_proof_coverage": _rate(
            [result for result in results if result.requires_relationship_proof],
            "relationship_match",
        ),
        "graph_proof_accuracy": _rate(results, "graph_proof_match"),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2),
        "p50_latency_ms": round(median(latencies), 2),
        "p95_latency_ms": _percentile(latencies, 0.95),
    }


def summarize_by_system(results: list[EvaluationResult]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        grouped[result.system].append(result)
    return {system: summarize(items) for system, items in grouped.items()}


def render_markdown(
    results: list[EvaluationResult],
    summary_by_system: dict[str, dict[str, Any]],
    contract_checks: list[dict[str, Any]] | None = None,
) -> str:
    """Create a concise, presentation-safe scorecard from machine-readable results."""

    lines = [
        "# RepoBrain Evaluation Scorecard",
        "",
        "This report scores graph proof, not fluent wording alone. A graph-proof pass requires the expected tool, evidence facts, source coverage, required relationship evidence, and expected warnings.",
        "",
        "## System comparison",
        "",
        "| System | Cases | Graph proof | Evidence facts | Sources | Tool selection | Relationship proof | p50 latency | p95 latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for system, values in summary_by_system.items():
        lines.append(
            "| {system} | {cases} | {graph:.1%} | {evidence:.1%} | {sources:.1%} | {tools:.1%} | {relationships:.1%} | {p50:.2f} ms | {p95:.2f} ms |".format(
                system=system,
                cases=values["cases"],
                graph=values["graph_proof_accuracy"],
                evidence=values["evidence_fact_accuracy"],
                sources=values["source_coverage"],
                tools=values["tool_selection_accuracy"],
                relationships=values["relationship_proof_coverage"],
                p50=values["p50_latency_ms"],
                p95=values["p95_latency_ms"],
            )
        )

    lines.extend([
        "",
        "## Case-level proof",
        "",
        "| Case | System | Tool | Evidence | Sources | Relationship | Graph proof |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for result in results:
        lines.append(
            "| {case_id} | {system} | {tool} | {evidence} | {sources} | {relationship} | {proof} |".format(
                case_id=result.case_id,
                system=result.system,
                tool="✓" if result.tool_match else "—",
                evidence="✓" if result.evidence_match else "—",
                sources="✓" if result.has_sources else "—",
                relationship="✓" if result.relationship_match else "—",
                proof="✓" if result.graph_proof_match else "—",
            )
        )

    if contract_checks:
        lines.extend([
            "",
            "## Contract checks",
            "",
            "| Check | Passed | Cleanup | Detail |",
            "| --- | --- | --- | --- |",
        ])
        for check in contract_checks:
            lines.append(
                "| {name} | {passed} | {cleanup} | {detail} |".format(
                    name=check.get("name", "unknown"),
                    passed="✓" if check.get("passed") else "—",
                    cleanup="✓" if check.get("cleaned_up") else "—",
                    detail=str(check.get("detail", "")).replace("|", "\\|"),
                )
            )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- **Verified facts** are accepted only when they appear in returned tool evidence with the required source coverage.",
        "- **Derived graph results** require their configured relationship or hop proof; impact analysis, for example, must expose a witness path.",
        "- **Model prose** is measured separately and cannot turn an unsupported baseline response into a graph-proof pass.",
    ])
    return "\n".join(lines) + "\n"
