"""Orchestrate routing, graph evidence collection, and answer generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.agent.ollama import OllamaClient, OllamaError
from app.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.agent.router import Route, route_question
from app.config import Settings, get_settings
from app.evidence.models import EvidenceBundle
from app.tools.graph_queries import GraphQueryError, GraphQueryTools
from app.mcp.gateway import DirectToolGateway, ToolCallTrace, ToolGateway, build_tool_gateway


@dataclass(frozen=True)
class AgentResponse:
    question: str
    intent: str
    answer: str
    evidence: EvidenceBundle | None
    model: str | None
    used_fallback: bool
    limitation: str | None = None
    execution_mode: str | None = None
    tool_calls: tuple[ToolCallTrace, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result


class ReasoningAgent:
    """A graph-first agent with deterministic tool boundaries and safe fallback."""

    def __init__(
        self,
        settings: Settings | None = None,
        tools: GraphQueryTools | None = None,
        ollama_client: OllamaClient | None = None,
        gateway: ToolGateway | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tools = tools
        self.gateway = gateway or (
            DirectToolGateway(tools)
            if tools is not None
            else build_tool_gateway(self.settings)
        )
        self.ollama = ollama_client or OllamaClient(
            self.settings.ollama_base_url,
            self.settings.agent_model,
            self.settings.agent_timeout_seconds,
        )

    def _run_tool(self, route: Route, snapshot_id: str | None, tenant_id: str) -> tuple[EvidenceBundle, ToolCallTrace]:
        args = dict(route.arguments)
        args["snapshot_id"] = snapshot_id
        if route.intent == "recall_context":
            args["tenant_id"] = tenant_id
        return self.gateway.invoke(route.intent, args)

    @staticmethod
    def _fallback_answer(question: str, evidence: EvidenceBundle) -> str:
        if not evidence.rows:
            if evidence.tool_name == "impact_analysis":
                warning = f" Warnings: {'; '.join(evidence.warnings)}" if evidence.warnings else ""
                return f"The graph found no static dependency paths for this file.{warning}"
            return "The selected repository snapshot does not contain evidence for that question."
        if evidence.tool_name == "impact_analysis":
            lines = ["Files affected through statically extracted Python dependencies:"]
            for row in evidence.rows:
                path = row.get("affected_file", "unknown file")
                hops = row.get("hop_distance", "?")
                witness = " -> ".join(str(item) for item in (row.get("witness_path") or []))
                lines.append(f"- {path} ({hops} hop(s)); path: {witness}")
            if evidence.warnings:
                lines.append("\nWarnings: " + "; ".join(evidence.warnings))
            lines.append(f"\nEvidence: tool={evidence.tool_name}; snapshot_id={evidence.snapshot_id}")
            return "\n".join(lines)
        if evidence.tool_name == "suggest_reviewers":
            has_review_history = any(int(row.get("review_count") or 0) > 0 for row in evidence.rows)
            basis = "file-change and verified pull-request review history" if has_review_history else "authored file-change history"
            lines = [f"Suggested reviewers from {basis}:"]
            for index, row in enumerate(evidence.rows, start=1):
                lines.append(
                    f"{index}. {row.get('display_name') or row.get('contributor')} "
                    f"({row.get('contributor')}); coverage={row.get('covered_files')}/"
                    f"{row.get('requested_file_count')}, commits={row.get('commit_count')}, "
                    f"reviews={row.get('review_count', 0)}, approvals={row.get('approval_count', 0)}, "
                    f"score={row.get('final_score')}"
                )
                paths = row.get("file_paths") or row.get("reviewed_file_paths") or []
                lines.append(f"   files: {', '.join(str(path) for path in paths)}")
            if evidence.warnings:
                lines.append("\nWarnings: " + "; ".join(evidence.warnings))
            lines.append(f"\nEvidence: tool={evidence.tool_name}; snapshot_id={evidence.snapshot_id}")
            return "\n".join(lines)
        if evidence.tool_name == "trace_decision":
            lines = ["Decision candidates supported by repository discussion evidence:"]
            for index, row in enumerate(evidence.rows, start=1):
                lines.append(
                    f"{index}. {row.get('statement')} "
                    f"(status={row.get('status')}, confidence={row.get('confidence')}, "
                    f"source={row.get('source_type')} {row.get('source_id')})"
                )
                excerpts = [str(item) for item in (row.get("evidence_excerpts") or []) if item]
                if excerpts:
                    lines.append(f"   evidence: {' | '.join(excerpts[:2])}")
                superseded = [str(item) for item in (row.get("superseded_statements") or []) if item]
                if superseded:
                    lines.append(f"   explicitly supersedes: {' | '.join(superseded[:2])}")
            if evidence.warnings:
                lines.append("\nWarnings: " + "; ".join(evidence.warnings))
            lines.append(f"\nEvidence: tool={evidence.tool_name}; snapshot_id={evidence.snapshot_id}")
            return "\n".join(lines)
        if evidence.tool_name == "recall_context":
            lines = ["Recalled user-owned findings:"]
            for index, row in enumerate(evidence.rows, start=1):
                lines.append(
                    f"{index}. {row.get('text')} "
                    f"(status={row.get('status')}, version={row.get('version')}, snapshot={row.get('snapshot_id') or 'unspecified'})"
                )
                if row.get("source_urls"):
                    lines.append(f"   sources: {', '.join(str(url) for url in row['source_urls'])}")
            if evidence.warnings:
                lines.append("\nWarnings: " + "; ".join(evidence.warnings))
            lines.append(f"\nEvidence: tool={evidence.tool_name}; tenant-filtered memory")
            return "\n".join(lines)
        if evidence.tool_name == "file_contributors" and evidence.derived_results:
            lines = ["Contributors and commit-level changes in the matching files:"]
            for index, row in enumerate(evidence.rows, start=1):
                lines.append(
                    f"{index}. {row.get('display_name') or row.get('contributor')} "
                    f"({row.get('contributor')}); commits={row.get('commit_count')}; "
                    f"files={', '.join(str(path) for path in (row.get('file_paths') or []))}"
                )
            lines.append("\nChange summaries:")
            for row in evidence.derived_results[:10]:
                lines.append(
                    f"- {row.get('file_path')} at {row.get('commit_sha')}: "
                    f"{row.get('commit_subject') or 'subject unavailable'}; "
                    f"status={row.get('change_status') or 'unknown'}, "
                    f"+{row.get('additions') or 0}/-{row.get('deletions') or 0}"
                )
            lines.append(
                f"\nEvidence: tool={evidence.tool_name}; snapshot_id={evidence.snapshot_id}; "
                "commit-level metadata, not line-level patch content"
            )
            return "\n".join(lines)
        if evidence.tool_name == "file_change_detail":
            lines = ["Line-level repository change evidence:"]
            for row in evidence.rows:
                patch_state = "available" if row.get("patch_available") else "unavailable"
                if row.get("patch_truncated"):
                    patch_state += " (stored excerpt is truncated)"
                lines.append(
                    f"- {row.get('file_path')} at {row.get('commit_sha')}: "
                    f"{row.get('commit_subject') or 'subject unavailable'}; "
                    f"{row.get('change_status') or 'unknown'}, "
                    f"+{row.get('additions') or 0}/-{row.get('deletions') or 0}; patch={patch_state}"
                )
            lines.append(
                f"\nEvidence: tool={evidence.tool_name}; snapshot_id={evidence.snapshot_id}; "
                "open the patch evidence panel for the exact unified diff."
            )
            return "\n".join(lines)
        first_rows = evidence.rows[:5]
        preview = "; ".join(
            ", ".join(f"{key}={value}" for key, value in row.items() if value is not None)
            for row in first_rows
        )
        return (
            f"The graph tool '{evidence.tool_name}' returned {len(evidence.rows)} evidence row(s) "
            f"for snapshot {evidence.snapshot_id}. The first result(s) are: {preview}"
        )

    @staticmethod
    def _answer_is_grounded(answer: str, evidence: EvidenceBundle) -> bool:
        """Reject obvious model drift before it reaches the user."""

        normalized = answer.casefold()
        if evidence.tool_name.casefold() not in normalized:
            return False
        if evidence.snapshot_id and evidence.snapshot_id.casefold() not in normalized:
            return False
        if evidence.tool_name == "file_contributors":
            contributors = {
                str(row.get("contributor"))
                for row in evidence.rows
                if row.get("contributor")
            }
            paths = {
                str(path)
                for row in evidence.rows
                for path in (row.get("file_paths") or [])
                if path
            }
            return all(value.casefold() in normalized for value in contributors) and all(
                value.casefold() in normalized for value in paths
            )
        if evidence.tool_name == "contributor_changes":
            contributors = {
                str(row.get("contributor"))
                for row in evidence.rows
                if row.get("contributor")
            }
            paths = {str(row.get("file_path")) for row in evidence.rows if row.get("file_path")}
            return all(value.casefold() in normalized for value in contributors) and any(
                value.casefold() in normalized for value in paths
            )
        if evidence.tool_name in {"file_history", "file_change_detail", "commit_impact"}:
            paths = {str(row.get("file_path")) for row in evidence.rows if row.get("file_path")}
            return any(value.casefold() in normalized for value in paths)
        if evidence.tool_name == "impact_analysis":
            paths = {str(row.get("affected_file")) for row in evidence.rows if row.get("affected_file")}
            return all(value.casefold() in normalized for value in paths)
        if evidence.tool_name == "suggest_reviewers":
            contributors = {str(row.get("contributor")) for row in evidence.rows if row.get("contributor")}
            return all(value.casefold() in normalized for value in contributors)
        if evidence.tool_name == "trace_decision":
            statements = [str(row.get("statement")) for row in evidence.rows if row.get("statement")]
            source_ids = [str(row.get("source_id")) for row in evidence.rows if row.get("source_id")]
            return bool(statements) and any(value.casefold() in normalized for value in statements) and any(
                value.casefold() in normalized for value in source_ids
            )
        if evidence.tool_name == "recall_context":
            finding_text = [str(row.get("text")) for row in evidence.rows if row.get("text")]
            return bool(finding_text) and any(value.casefold() in normalized for value in finding_text)
        if evidence.tool_name == "snapshot_overview" and evidence.rows:
            repository = evidence.rows[0].get("repository")
            return not repository or str(repository).casefold() in normalized
        return True

    def answer(
        self,
        question: str,
        snapshot_id: str | None = None,
        tenant_id: str = "tenant_demo_alpha",
    ) -> AgentResponse:
        route = route_question(question)
        if route.intent == "unsupported":
            return AgentResponse(
                question=question,
                intent=route.intent,
                answer=(
                    "I cannot safely answer that with the current read-only graph tools. "
                    "Try asking about a repository overview, file history, file contributors, "
                    "a contributor's changed files, or a commit's affected files."
                ),
                evidence=None,
                model=None,
                used_fallback=True,
                limitation=route.reason,
                execution_mode=None,
            )

        try:
            evidence, trace = self._run_tool(route, snapshot_id, tenant_id)
        except (GraphQueryError, ValueError) as exc:
            return AgentResponse(
                question=question,
                intent=route.intent,
                answer=f"I could not obtain verified graph evidence: {exc}",
                evidence=None,
                model=None,
                used_fallback=True,
                limitation=str(exc),
                execution_mode=getattr(self.gateway, "mode", None),
            )

        if not evidence.has_evidence:
            return AgentResponse(
                question=question,
                intent=route.intent,
                answer="The selected repository snapshot does not contain evidence for that question.",
                evidence=evidence,
                model=None,
                used_fallback=True,
                limitation="empty graph result",
                execution_mode=trace.execution_mode,
                tool_calls=(trace,),
            )

        try:
            answer = self.ollama.generate(SYSTEM_PROMPT, build_user_prompt(question, evidence))
            if not self._answer_is_grounded(answer, evidence):
                return AgentResponse(
                    question=question,
                    intent=route.intent,
                    answer=self._fallback_answer(question, evidence),
                    evidence=evidence,
                    model=self.ollama.model,
                    used_fallback=True,
                    limitation="model answer failed evidence consistency checks",
                    execution_mode=trace.execution_mode,
                    tool_calls=(trace,),
                )
            return AgentResponse(
                question=question,
                intent=route.intent,
                answer=answer,
                evidence=evidence,
                model=self.ollama.model,
                used_fallback=False,
                execution_mode=trace.execution_mode,
                tool_calls=(trace,),
            )
        except OllamaError as exc:
            return AgentResponse(
                question=question,
                intent=route.intent,
                answer=self._fallback_answer(question, evidence),
                evidence=evidence,
                model=self.ollama.model,
                used_fallback=True,
                limitation=str(exc),
                execution_mode=trace.execution_mode,
                tool_calls=(trace,),
            )
