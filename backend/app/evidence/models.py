"""Serializable evidence bundles returned by graph tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceBundle:
    """The exact graph evidence used for one agent step."""

    tool_name: str
    query: str
    parameters: dict[str, Any]
    columns: list[str]
    rows: list[dict[str, Any]]
    snapshot_id: str | None
    source_urls: list[str] = field(default_factory=list)
    snapshot_selector_query: str | None = None
    result_type: str = "verified"
    warnings: list[str] = field(default_factory=list)
    derived_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return bool(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvidenceBundle":
        return cls(
            tool_name=str(value["tool_name"]),
            query=str(value["query"]),
            parameters=dict(value.get("parameters", {})),
            columns=[str(column) for column in value.get("columns", [])],
            rows=[dict(row) for row in value.get("rows", [])],
            snapshot_id=value.get("snapshot_id"),
            source_urls=[str(url) for url in value.get("source_urls", [])],
            snapshot_selector_query=value.get("snapshot_selector_query"),
            result_type=str(value.get("result_type", "verified")),
            warnings=[str(item) for item in value.get("warnings", [])],
            derived_results=[dict(item) for item in value.get("derived_results", [])],
        )

    def to_prompt_context(self, max_rows: int = 30) -> str:
        """Render bounded, structured evidence for the answer model."""

        rows = self.rows[:max_rows]
        lines = [
            f"tool={self.tool_name}",
            f"snapshot_id={self.snapshot_id or 'unknown'}",
            f"columns={', '.join(self.columns)}",
            f"row_count={len(self.rows)}",
            f"result_type={self.result_type}",
            "rows:",
        ]
        for index, row in enumerate(rows, start=1):
            prompt_row = dict(row)
            patch = prompt_row.get("patch")
            if isinstance(patch, str):
                prompt_row["patch"] = (
                    f"[stored patch omitted from model prompt; {len(patch)} characters; "
                    "inspect in the evidence panel]"
                )
            lines.append(f"{index}. {prompt_row}")
        if len(self.rows) > max_rows:
            lines.append(f"... {len(self.rows) - max_rows} additional rows omitted")
        if self.derived_results:
            derived = self.derived_results[:max_rows]
            lines.append("supporting_change_rows:")
            for index, row in enumerate(derived, start=1):
                lines.append(f"{index}. {row}")
            if len(self.derived_results) > max_rows:
                lines.append(f"... {len(self.derived_results) - max_rows} additional supporting rows omitted")
        if self.source_urls:
            lines.append("source_urls:")
            lines.extend(f"- {url}" for url in self.source_urls)
        if self.warnings:
            lines.append("warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)
