"""Run both subjects with and without coverage feedback. Writes artifacts/summary.json."""

from __future__ import annotations

import json
from pathlib import Path

from testgen.pipeline import project_root, run_loop

SUBJECTS = [
    ("subjects.shipping", "shipping_fee", "运费计算"),
    ("subjects.access_control", "access_decision", "门禁判定"),
]


def _dump(history) -> list[dict]:
    return [
        {
            "iteration": item.iteration,
            "test_count": item.test_count,
            "new_tests": item.new_tests,
            "statement_percent": round(item.statement_percent, 1),
            "branch_percent": round(item.branch_percent, 1),
            "missing_lines": item.missing_lines,
            "missing_branches": item.missing_branches,
            "pytest_passed": item.pytest_passed,
            "pytest_output": item.pytest_output.strip(),
        }
        for item in history
    ]


def main() -> None:
    root = project_root()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    summary = {"provider": "mock", "live_api": False, "subjects": []}
    for module_name, function_name, title in SUBJECTS:
        subject = {"module": module_name, "function": function_name, "title": title, "modes": {}}
        for mode, use_feedback in (("feedback", True), ("blind", False)):
            out = artifacts / f"{function_name}_{mode}"
            history = run_loop(
                module_name=module_name,
                function_name=function_name,
                out_dir=out,
                max_rounds=8,
                target=100.0,
                provider_name="mock",
                use_feedback=use_feedback,
            )
            subject["modes"][mode] = _dump(history)
        summary["subjects"].append(subject)
    destination = artifacts / "summary.json"
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
