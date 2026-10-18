"""Command-line interface for deterministic repository ingestion."""

from __future__ import annotations

import argparse
import json

from app.config import get_settings
from app.ingestion.pipeline import ingest_repository
from app.ingestion.dependency_enricher import DependencyEnricher
from app.ingestion.review_enricher import ReviewEnricher
from app.ingestion.decision_enricher import DecisionEnricher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest a pinned GitHub repository snapshot into FalkorDB.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="fetch and load one repository snapshot")
    ingest.add_argument("--repo", help="owner/name override")
    ingest.add_argument("--sha", help="exact commit SHA override")
    ingest.add_argument("--commit-limit", type=int, help="maximum recent commits")
    ingest.add_argument("--max-files", type=int, help="maximum files allowed in the tree")
    enrich = subparsers.add_parser("enrich-dependencies", help="extract static Python dependency edges")
    enrich.add_argument("--snapshot", help="exact complete snapshot ID; defaults to the latest")
    reviews = subparsers.add_parser("enrich-reviews", help="ingest bounded pull-request and review history")
    reviews.add_argument("--snapshot", help="exact complete snapshot ID; defaults to the latest")
    reviews.add_argument("--pr-limit", type=int, help="maximum pull requests to inspect")
    decisions = subparsers.add_parser("enrich-decisions", help="ingest bounded decision evidence from GitHub discussions")
    decisions.add_argument("--snapshot", help="exact complete snapshot ID; defaults to the latest")
    decisions.add_argument("--source-limit", type=int, help="maximum issues and pull requests to inspect")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    updates = {}
    if getattr(args, "repo", None):
        updates["target_repo"] = args.repo
    if getattr(args, "sha", None):
        updates["target_sha"] = args.sha
    if getattr(args, "commit_limit", None):
        updates["snapshot_commit_limit"] = args.commit_limit
    if getattr(args, "max_files", None):
        updates["snapshot_max_files"] = args.max_files
    if updates:
        settings = settings.model_copy(update=updates)

    if args.command == "ingest":
        data, counts = ingest_repository(settings)
        print(json.dumps({"snapshot": data.snapshot["id"], "status": "complete", **counts}, indent=2))
    elif args.command == "enrich-dependencies":
        result = DependencyEnricher(settings=settings).enrich(args.snapshot)
        print(json.dumps(result, indent=2))
    elif args.command == "enrich-reviews":
        result = ReviewEnricher(settings=settings).enrich(args.snapshot, args.pr_limit)
        print(json.dumps(result, indent=2))
    elif args.command == "enrich-decisions":
        result = DecisionEnricher(settings=settings).enrich(args.snapshot, args.source_limit)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

