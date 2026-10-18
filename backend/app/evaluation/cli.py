"""Run the small golden-question evaluation set."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.agent.orchestrator import ReasoningAgent
from app.config import Settings
from app.evaluation.fixtures import load_cases
from app.evaluation.baseline import score_baseline
from app.evaluation.memory_contract import run_tenant_isolation_check
from app.evaluation.scorer import render_markdown, score_agent, summarize_by_system


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RepoBrain graph-backed answers")
    parser.add_argument("--fixture", type=Path, default=Path("data/evaluation/golden_questions.jsonl"))
    parser.add_argument("--mode", choices=("mcp", "direct"), default=None)
    parser.add_argument("--output", type=Path, default=Path("outputs/evaluation/latest_run.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("outputs/evaluation/latest_run.md"))
    parser.add_argument("--include-baseline", action="store_true")
    parser.add_argument(
        "--include-memory-isolation-check",
        action="store_true",
        help="Create and delete one temporary tenant-owned finding to verify isolation.",
    )
    args = parser.parse_args()
    settings = Settings(tool_mode=args.mode or Settings().tool_mode)
    agent = ReasoningAgent(settings=settings)
    cases = load_cases(args.fixture)
    results = [score_agent(case, agent, "repobrain") for case in cases]
    if args.include_baseline:
        baseline = agent.ollama
        results.extend(score_baseline(case, baseline) for case in cases)
    contract_checks = []
    if args.include_memory_isolation_check:
        contract_checks.append(run_tenant_isolation_check(settings=settings).to_dict())
    payload = {
        "fixture": str(args.fixture),
        "execution_mode": settings.tool_mode,
        "summary_by_system": summarize_by_system(results),
        "results": [asdict(item) for item in results],
        "contract_checks": contract_checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(
        render_markdown(results, payload["summary_by_system"], contract_checks),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary_by_system"], indent=2))
    print(f"JSON report: {args.output}")
    print(f"Markdown scorecard: {args.markdown_output}")


if __name__ == "__main__":
    main()

