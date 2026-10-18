"""Opt-in live contract checks for tenant-isolated graph memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from app.config import Settings, get_settings
from app.evidence.models import EvidenceBundle
from app.graph.connection import get_graph
from app.memory.models import FindingCreate
from app.memory.repository import MemoryRepository


@dataclass(frozen=True)
class TenantIsolationCheck:
    name: str
    passed: bool
    alpha_can_recall: bool
    beta_can_recall: bool
    cleaned_up: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains_finding(evidence: EvidenceBundle, finding_id: str) -> bool:
    return any(str(row.get("finding_id")) == finding_id for row in evidence.rows)


def run_tenant_isolation_check(
    repository: MemoryRepository | None = None,
    settings: Settings | None = None,
) -> TenantIsolationCheck:
    """Create and remove one private probe; never inspect ordinary user findings."""

    active_settings = settings or get_settings()
    memory = repository or MemoryRepository(get_graph(active_settings), settings=active_settings)
    graph = memory.graph
    probe = f"repobrain-evaluation-tenant-probe-{uuid4().hex}"
    finding_id: str | None = None
    cleaned_up = False
    alpha_can_recall = False
    beta_can_recall = False
    detail = "A temporary Alpha finding was queried from both controlled tenants."
    try:
        created = memory.create_finding(
            "tenant_demo_alpha",
            FindingCreate(text=probe, idempotency_key=probe),
        )
        finding_id = str(created["finding_id"])
        alpha = memory.recall_context("tenant_demo_alpha", probe, limit=10)
        beta = memory.recall_context("tenant_demo_beta", probe, limit=10)
        alpha_can_recall = _contains_finding(alpha, finding_id)
        beta_can_recall = _contains_finding(beta, finding_id)
    except Exception as exc:
        detail = f"The controlled memory check could not run: {type(exc).__name__}."
    finally:
        if finding_id:
            try:
                graph.query(
                    """
                    MATCH (f:Finding {id: $finding_id, tenant_id: 'tenant_demo_alpha'})
                    DETACH DELETE f
                    """,
                    {"finding_id": finding_id},
                )
                cleaned_up = True
            except Exception:
                cleaned_up = False
    return TenantIsolationCheck(
        name="tenant-memory-isolation",
        passed=alpha_can_recall and not beta_can_recall and cleaned_up,
        alpha_can_recall=alpha_can_recall,
        beta_can_recall=beta_can_recall,
        cleaned_up=cleaned_up,
        detail=detail,
    )
