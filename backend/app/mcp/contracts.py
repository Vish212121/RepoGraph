"""Stable names and trace contracts shared by MCP clients and the agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.evidence.models import EvidenceBundle

INTENT_TO_TOOL = {
    "snapshot_overview": "repobrain_snapshot_overview",
    "list_snapshots": "repobrain_list_snapshots",
    "contributor_changes": "repobrain_contributor_changes",
    "file_contributors": "repobrain_file_contributors",
    "file_history": "repobrain_file_history",
    "file_change_detail": "repobrain_file_change_detail",
    "commit_impact": "repobrain_commit_impact",
    "impact_analysis": "repobrain_impact_analysis",
    "suggest_reviewers": "repobrain_suggest_reviewers",
    "trace_decision": "repobrain_trace_decision",
    "recall_context": "repobrain_recall_context",
}


@dataclass(frozen=True)
class ToolCallTrace:
    execution_mode: Literal["mcp", "direct"]
    tool_name: str
    arguments: dict[str, Any]
    result_rows: int


@dataclass(frozen=True)
class ToolInvocation:
    evidence: EvidenceBundle
    trace: ToolCallTrace

