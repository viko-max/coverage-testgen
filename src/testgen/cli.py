"""Command line entry. Default provider is mock; live API keys are not used."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testgen.llm import load_project_env
from testgen.pipeline import project_root, run_loop


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate pytest cases from coverage feedback.")
    parser.add_argument("--module", required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--provider", default="mock", choices=["mock", "neohorse"])
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--target", type=float, default=100.0)
    parser.add_argument("--no-feedback", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.provider == "neohorse":
        load_project_env()
    out = args.out or project_root() / "artifacts" / f"{args.function}_{args.provider}"
    history = run_loop(
        module_name=args.module,
        function_name=args.function,
        out_dir=out,
        max_rounds=args.max_rounds,
        target=args.target,
        provider_name=args.provider,
        use_feedback=not args.no_feedback,
    )
    summary = [
        {
            "iteration": item.iteration,
            "tests": item.test_count,
            "statement_percent": round(item.statement_percent, 1),
            "branch_percent": round(item.branch_percent, 1),
            "passed": item.pytest_passed,
            "missing_lines": item.missing_lines,
        }
        for item in history
    ]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
