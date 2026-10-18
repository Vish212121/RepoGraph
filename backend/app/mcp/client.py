"""Small synchronous adapter around the official MCP Python client."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters

from app.config import Settings
from app.evidence.models import EvidenceBundle
from app.tools.graph_queries import GraphQueryError


class MCPGraphClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _server_parameters(self) -> StdioServerParameters:
        command = self.settings.mcp_server_command
        if command.lower() in {"python", "python.exe"}:
            command = sys.executable
        project_root = Path(__file__).resolve().parents[3]
        env = dict(os.environ)
        inherited = env.get("PYTHONPATH", "")
        paths = [str(project_root / "backend"), str(project_root / ".vendor")]
        if inherited:
            paths.append(inherited)
        env["PYTHONPATH"] = os.pathsep.join(paths)
        env["REPOBRAIN_TOOL_MODE"] = "direct"
        return StdioServerParameters(
            command=command,
            args=["-m", self.settings.mcp_server_module],
            env=env,
            cwd=str(project_root),
        )

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> EvidenceBundle:
        server = self._server_parameters()
        async with Client(server, read_timeout_seconds=self.settings.mcp_timeout_seconds) as client:
            result = await client.call_tool(name, arguments)
        if getattr(result, "isError", False):
            raise GraphQueryError(f"MCP tool {name} returned an error")
        payload: str | None = None
        for content in getattr(result, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                payload = text
                break
        if payload is None:
            structured = getattr(result, "structuredContent", None)
            payload = json.dumps(structured) if structured is not None else None
        if not payload:
            raise GraphQueryError(f"MCP tool {name} returned no content")
        try:
            return EvidenceBundle.from_dict(json.loads(payload))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise GraphQueryError(f"MCP tool {name} returned invalid evidence: {exc}") from exc

    def call_tool(self, name: str, arguments: dict[str, Any]) -> EvidenceBundle:
        try:
            return asyncio.run(self._call_async(name, arguments))
        except GraphQueryError:
            raise
        except Exception as exc:
            raise GraphQueryError(f"MCP tool {name} failed: {exc}") from exc

