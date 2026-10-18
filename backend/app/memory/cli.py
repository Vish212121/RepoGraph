"""Maintenance commands for RepoBrain's persisted graph memory."""

from __future__ import annotations

import argparse
import json

from app.config import get_settings
from app.graph.connection import get_graph
from app.memory.repository import MemoryRepository
from app.tenant import resolve_demo_tenant


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain RepoBrain's graph-backed tenant memory.")
    commands = parser.add_subparsers(dest="command", required=True)
    backfill = commands.add_parser("backfill", help="Generate local embeddings for saved findings.")
    backfill.add_argument("--tenant", choices=("demo-alpha", "demo-beta"), default="demo-alpha")
    backfill.add_argument("--limit", type=int, default=100)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command != "backfill":
        raise SystemExit(f"Unsupported memory command: {args.command}")

    settings = get_settings()
    repository = MemoryRepository(get_graph(settings), settings=settings)
    result = repository.backfill_embeddings(resolve_demo_tenant(args.tenant), args.limit)
    print(json.dumps({"tenant": args.tenant, **result}, indent=2))


if __name__ == "__main__":
    main()
