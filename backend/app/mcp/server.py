"""Read-only MCP server exposing RepoBrain's bounded graph operations."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer

from app.config import get_settings
from app.tools.graph_queries import GraphQueryTools
from app.memory.models import FindingCreate, FindingUpdate

mcp = MCPServer(
    "RepoBrain Graph Tools",
    instructions="Read-only, snapshot-bound graph evidence tools for RepoBrain.",
)


def _tools() -> GraphQueryTools:
    return GraphQueryTools(settings=get_settings())


def _json(evidence: Any) -> str:
    return json.dumps(evidence.to_dict(), default=str)


@mcp.tool()
def repobrain_snapshot_overview(snapshot_id: str | None = None) -> str:
    return _json(_tools().snapshot_overview(snapshot_id))


@mcp.tool()
def repobrain_list_snapshots(limit: int = 20) -> str:
    return _json(_tools().list_snapshots(limit))


@mcp.tool()
def repobrain_contributor_changes(
    contributor: str, snapshot_id: str | None = None, limit: int = 20
) -> str:
    return _json(_tools().contributor_changes(contributor, snapshot_id, limit))


@mcp.tool()
def repobrain_file_contributors(
    path_fragment: str, snapshot_id: str | None = None, limit: int = 20
) -> str:
    return _json(_tools().file_contributors(path_fragment, snapshot_id, limit))


@mcp.tool()
def repobrain_file_history(
    path_fragment: str, snapshot_id: str | None = None, limit: int = 30
) -> str:
    return _json(_tools().file_history(path_fragment, snapshot_id, limit))


@mcp.tool()
def repobrain_file_change_detail(
    path_fragment: str, snapshot_id: str | None = None, limit: int = 10
) -> str:
    return _json(_tools().file_change_detail(path_fragment, snapshot_id, limit))


@mcp.tool()
def repobrain_commit_impact(
    commit_prefix: str, snapshot_id: str | None = None, limit: int = 50
) -> str:
    return _json(_tools().commit_impact(commit_prefix, snapshot_id, limit))


@mcp.tool()
def repobrain_impact_analysis(
    file_path: str,
    snapshot_id: str | None = None,
    max_hops: int = 3,
    limit: int = 25,
) -> str:
    return _json(_tools().impact_analysis(file_path, snapshot_id, max_hops, limit))


@mcp.tool()
def repobrain_suggest_reviewers(
    file_paths: list[str],
    snapshot_id: str | None = None,
    limit: int = 5,
    exclude_logins: list[str] | None = None,
) -> str:
    return _json(_tools().suggest_reviewers(file_paths, snapshot_id, limit, exclude_logins))


@mcp.tool()
def repobrain_trace_decision(
    topic: str, snapshot_id: str | None = None, limit: int = 10
) -> str:
    return _json(_tools().trace_decision(topic, snapshot_id, limit))


@mcp.tool()
def repobrain_recall_context(
    tenant_id: str, query: str, snapshot_id: str | None = None, limit: int = 10
) -> str:
    return _json(_tools().recall_context(tenant_id, query, snapshot_id, limit))


@mcp.tool()
def repobrain_create_finding(
    tenant_id: str,
    text: str,
    references: list[dict[str, str]] | None = None,
    source_urls: list[str] | None = None,
    snapshot_id: str | None = None,
    session_id: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    result = _tools().create_finding(
        tenant_id,
        FindingCreate(
            text=text,
            references=references or [],
            source_urls=source_urls or [],
            snapshot_id=snapshot_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        ),
    )
    return json.dumps(result, default=str)


@mcp.tool()
def repobrain_update_finding(
    tenant_id: str,
    finding_id: str,
    expected_version: int,
    text: str | None = None,
    status: str | None = None,
) -> str:
    result = _tools().update_finding(
        tenant_id,
        finding_id,
        FindingUpdate(text=text, status=status, expected_version=expected_version),
    )
    return json.dumps(result, default=str)


if __name__ == "__main__":
    mcp.run("stdio")

