"""Command-line entry point for the Milestone 4 reasoning demonstration."""

from __future__ import annotations

import argparse
import json

from app.agent.orchestrator import ReasoningAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask RepoBrain a FalkorDB-backed repository question")
    parser.add_argument("question", nargs="+", help="natural-language repository question")
    parser.add_argument("--snapshot", help="exact Snapshot.id; defaults to the latest complete snapshot")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print the full response as JSON")
    args = parser.parse_args()

    response = ReasoningAgent().answer(" ".join(args.question), snapshot_id=args.snapshot)
    if args.as_json:
        print(json.dumps(response.to_dict(), indent=2, default=str))
        return
    print(response.answer)
    if response.evidence:
        print(f"\nGraph tool: {response.evidence.tool_name}")
        print(f"Snapshot: {response.evidence.snapshot_id}")
        print(f"Rows: {len(response.evidence.rows)}")
        if response.evidence.source_urls:
            print("Sources:")
            for source in response.evidence.source_urls:
                print(f"- {source}")
    if response.limitation:
        print(f"\nLimitation: {response.limitation}")


if __name__ == "__main__":
    main()
