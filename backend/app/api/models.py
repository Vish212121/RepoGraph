"""Stable HTTP request and response models for RepoBrain."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.agent.orchestrator import AgentResponse
from app.memory.models import FindingCreate, FindingUpdate


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    snapshot_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must contain text")
        return value


class EvidenceResponse(BaseModel):
    tool_name: str
    query: str
    parameters: dict[str, Any]
    columns: list[str]
    rows: list[dict[str, Any]]
    snapshot_id: str | None
    source_urls: list[str]
    snapshot_selector_query: str | None
    result_type: str = "verified"
    warnings: list[str] = Field(default_factory=list)
    derived_results: list[dict[str, Any]] = Field(default_factory=list)


class QueryResponse(BaseModel):
    question: str
    intent: str
    answer: str
    evidence: EvidenceResponse | None
    model: str | None
    used_fallback: bool
    limitation: str | None
    execution_mode: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None

    @classmethod
    def from_agent(cls, response: AgentResponse) -> "QueryResponse":
        evidence = None
        if response.evidence is not None:
            evidence = EvidenceResponse.model_validate(response.evidence.to_dict())
        return cls(
            question=response.question,
            intent=response.intent,
            answer=response.answer,
            evidence=evidence,
            model=response.model,
            used_fallback=response.used_fallback,
            limitation=response.limitation,
            execution_mode=response.execution_mode,
            tool_calls=[asdict(call) for call in response.tool_calls],
        )


class FindingResponse(BaseModel):
    finding_id: str
    text: str
    status: str
    version: int
    snapshot_id: str | None = None
    created_at: str
    updated_at: str
    references: list[dict[str, Any]] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    session_id: str | None = None
    embedding_status: str = "unknown"


class SnapshotResponse(BaseModel):
    repository: str | None = None
    repository_url: str | None = None
    snapshot_id: str
    commit_sha: str | None = None
    captured_at: str | None = None
    file_count: int | None = None
    commit_count: int | None = None
    snapshot_url: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    graph_configured: bool
    ollama_configured: bool
