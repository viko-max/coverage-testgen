"""Run pytest under coverage and read statement plus branch gaps."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from testgen.models import BranchGap, Feedback


def write_test_module(path: Path, module_name: str, function_name: str, tests: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(test.strip() for test in tests)
    content = f"import pytest\nfrom {module_name} import {function_name}\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


def run_coverage(project_root: Path, test_path: Path, work_dir: Path, source_file: Path) -> tuple[Feedback, bool, str]:
    work_dir.mkdir(parents=True, exist_ok=True)
    data_file = work_dir / ".coverage"
    json_file = work_dir / "coverage.json"
    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        f"--data-file={data_file}",
        "--branch",
        "--source=subjects",
        "-m",
        "pytest",
        str(test_path),
        "-q",
        "--tb=short",
    ]
    completed = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    (work_dir / "pytest.txt").write_text(output, encoding="utf-8")
    json_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "json",
        f"--data-file={data_file}",
        "-o",
        str(json_file),
        "--pretty-print",
    ]
    subprocess.run(json_cmd, cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    feedback = _read_feedback(json_file, source_file)
    return feedback, completed.returncode == 0, output


def _read_feedback(json_file: Path, source_file: Path) -> Feedback:
    if not json_file.exists():
        return Feedback()
    payload = json.loads(json_file.read_text(encoding="utf-8"))
    entry = _match_file(payload.get("files", {}), source_file)
    if entry is None:
        return Feedback()
    summary = entry.get("summary", {})
    source_lines = source_file.read_text(encoding="utf-8").splitlines()
    missing = [int(number) for number in entry.get("missing_lines", [])]
    texts = []
    for number in missing:
        texts.append(source_lines[number - 1].strip() if 1 <= number <= len(source_lines) else "")
    branches = []
    for pair in entry.get("missing_branches", []):
        branches.append(BranchGap(source_line=int(pair[0]), dest_line=int(pair[1])))
    num_statements = int(summary.get("num_statements") or 0)
    covered_lines = int(summary.get("covered_lines") or 0)
    num_branches = int(summary.get("num_branches") or 0)
    covered_branches = int(summary.get("covered_branches") or 0)
    statement_percent = 100.0 * covered_lines / num_statements if num_statements else 0.0
    branch_percent = 100.0 * covered_branches / num_branches if num_branches else 0.0
    return Feedback(
        statement_percent=statement_percent,
        branch_percent=branch_percent,
        missing_lines=missing,
        missing_line_text=texts,
        missing_branches=branches,
    )


def _match_file(files: dict, source_file: Path) -> dict | None:
    target = source_file.resolve()
    for raw_path, entry in files.items():
        if Path(raw_path).resolve() == target:
            return entry
    suffix = source_file.name
    for raw_path, entry in files.items():
        if raw_path.replace("\\", "/").endswith(suffix):
            return entry
    return None
