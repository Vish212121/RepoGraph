"""Validated demo-tenant mapping for user-owned memory."""

from __future__ import annotations


_TENANTS = {
    "demo-alpha": "tenant_demo_alpha",
    "demo-beta": "tenant_demo_beta",
}


def resolve_demo_tenant(value: str | None) -> str:
    alias = (value or "demo-alpha").strip().lower()
    try:
        return _TENANTS[alias]
    except KeyError as exc:
        raise ValueError("tenant must be one of: demo-alpha, demo-beta") from exc


def tenant_aliases() -> tuple[str, ...]:
    return tuple(_TENANTS)
