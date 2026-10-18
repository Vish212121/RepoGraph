"""Deterministic routing from repository questions to approved graph tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Route:
    """A validated intent and the arguments needed by one graph tool."""

    intent: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def _file_fragment(question: str) -> str | None:
    matches = re.findall(r"[A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.-]+)+|[A-Za-z0-9_.-]+\.[A-Za-z0-9_]+", question)
    return matches[0].strip(".,?()") if matches else None


def _contributor(question: str) -> str | None:
    patterns = (
        r"\b(?:by|from|contributor|author(?:ed)?)\s+([A-Za-z0-9_.-]+)",
        r"\bdid\s+([A-Za-z0-9_.-]+)\s+(?:change|modify|edit)",
    )
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _commit_prefix(question: str) -> str | None:
    matches = re.findall(r"\b[0-9a-f]{7,40}\b", question, flags=re.IGNORECASE)
    return matches[0] if matches else None


def route_question(question: str) -> Route:
    """Route common repository questions without allowing free-form Cypher."""

    normalized = question.strip()
    if not normalized:
        raise ValueError("question must not be empty")
    lower = normalized.lower()
    path = _file_fragment(normalized)
    contributor = _contributor(normalized)
    commit_prefix = _commit_prefix(normalized)

    if path and any(
        phrase in lower
        for phrase in (
            "what exactly changed", "what changed", "what changes were made", "show the diff",
            "show diff", "show the patch", "show patch", "which lines changed", "line changes",
        )
    ):
        return Route("file_change_detail", {"path_fragment": path}, "line-level change language plus a file path")
    if commit_prefix and any(word in lower for word in ("commit", "change", "impact", "affected")):
        return Route("commit_impact", {"commit_prefix": commit_prefix}, "commit SHA and impact language")
    if path and any(word in lower for word in ("impact", "affected", "dependents", "downstream", "rely on", "break")):
        return Route("impact_analysis", {"file_path": path}, "impact language plus a file path")
    if path and any(word in lower for word in ("review", "reviewer", "approve")):
        return Route("suggest_reviewers", {"file_paths": [path]}, "review language plus a file path")
    if any(
        phrase in lower
        for phrase in ("previously", "remember", "recall", "last session", "saved finding", "what did i find")
    ):
        return Route("recall_context", {"query": normalized}, "persistent-memory language")
    if any(
        phrase in lower
        for phrase in ("why was", "why does", "what decision", "which approach", "what design")
    ) or any(word in lower for word in ("superseded", "supersede", "replaced", "deprecated decision")):
        return Route("trace_decision", {"topic": normalized}, "decision or design-tracing language")
    if any(word in lower for word in ("history", "historical", "evolution", "changed over time")) and path:
        return Route("file_history", {"path_fragment": path}, "history language plus a file path")
    if any(word in lower for word in ("who", "contributor", "contributors", "author", "authors")) and path:
        return Route("file_contributors", {"path_fragment": path}, "people language plus a file path")
    if any(word in lower for word in ("what files", "which files", "files did", "changed files")) and contributor:
        return Route("contributor_changes", {"contributor": contributor}, "file-change language plus a contributor")
    if any(word in lower for word in ("overview", "snapshot", "repository size", "how many files", "how many commits")):
        return Route("snapshot_overview", {}, "repository summary language")
    return Route("unsupported", {}, "no safe graph intent matched")
