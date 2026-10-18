"""Small models used by the memory repository and API boundary."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FindingReference(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=500)


class FindingCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)
    references: list[FindingReference] = Field(default_factory=list, max_length=50)
    source_urls: list[str] = Field(default_factory=list, max_length=50)
    snapshot_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=200)


class FindingUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=4_000)
    status: str | None = Field(default=None, pattern=r"^(active|archived|stale)$")
    expected_version: int = Field(ge=1)


def finding_row(value: dict[str, Any]) -> dict[str, Any]:
    return {
        **value,
        "references": value.get("references", []),
        "source_urls": value.get("source_urls", []),
    }
