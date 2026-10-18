"""Direct and MCP-backed adapters for RepoBrain's graph tool boundary."""

from __future__ import annotations

from typing import Any, Protocol

from app.config import Settings
from app.evidence.models import EvidenceBundle
from app.mcp.client import MCPGraphClient
from app.mcp.contracts import INTENT_TO_TOOL, ToolCallTrace
from app.tools.graph_queries import GraphQueryError, GraphQueryTools


class ToolGateway(Protocol):
    mode: str

    def invoke(self, intent: str, arguments: dict[str, Any]) -> tuple[EvidenceBundle, ToolCallTrace]: ...


class DirectToolGateway:
    mode = "direct"

    def __init__(self, tools: GraphQueryTools | None = None) -> None:
        self.tools = tools or GraphQueryTools()

    def invoke(self, intent: str, arguments: dict[str, Any]) -> tuple[EvidenceBundle, ToolCallTrace]:
        method = {
            "snapshot_overview": lambda: self.tools.snapshot_overview(arguments.get("snapshot_id")),
            "list_snapshots": lambda: self.tools.list_snapshots(arguments.get("limit", 20)),
            "contributor_changes": lambda: self.tools.contributor_changes(**arguments),
            "file_contributors": lambda: self.tools.file_contributors(**arguments),
            "file_history": lambda: self.tools.file_history(**arguments),
            "file_change_detail": lambda: self.tools.file_change_detail(**arguments),
            "commit_impact": lambda: self.tools.commit_impact(**arguments),
            "impact_analysis": lambda: self.tools.impact_analysis(**arguments),
            "suggest_reviewers": lambda: self.tools.suggest_reviewers(**arguments),
            "trace_decision": lambda: self.tools.trace_decision(**arguments),
            "recall_context": lambda: self.tools.recall_context(**arguments),
        }.get(intent)
        if method is None:
            raise GraphQueryError(f"Unsupported intent: {intent}")
        evidence = method()
        trace = ToolCallTrace("direct", INTENT_TO_TOOL.get(intent, intent), arguments, len(evidence.rows))
        return evidence, trace


class MCPToolGateway:
    mode = "mcp"

    def __init__(self, client: MCPGraphClient) -> None:
        self.client = client

    def invoke(self, intent: str, arguments: dict[str, Any]) -> tuple[EvidenceBundle, ToolCallTrace]:
        tool_name = INTENT_TO_TOOL.get(intent)
        if tool_name is None:
            raise GraphQueryError(f"Unsupported intent: {intent}")
        evidence = self.client.call_tool(tool_name, arguments)
        trace = ToolCallTrace("mcp", tool_name, arguments, len(evidence.rows))
        return evidence, trace


def build_tool_gateway(settings: Settings, tools: GraphQueryTools | None = None) -> ToolGateway:
    if settings.tool_mode == "direct":
        return DirectToolGateway(tools)
    return MCPToolGateway(MCPGraphClient(settings))

