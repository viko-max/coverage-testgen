"""Iterative loop: generate, execute, feed uncovered paths back."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from testgen.coverage_runner import run_coverage, write_test_module
from testgen.llm import Provider, build_provider
from testgen.models import Feedback, GenerationContext, GeneratedTest, RoundResult
from testgen.prompts import render_prompt


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_loop(
    module_name: str,
    function_name: str,
    out_dir: Path,
    max_rounds: int = 8,
    target: float = 100.0,
    provider_name: str = "mock",
    use_feedback: bool = True,
    provider: Provider | None = None,
) -> list[RoundResult]:
    if provider_name not in {"mock", "neohorse", "openai"} and provider is None:
        raise RuntimeError(f"unknown provider: {provider_name}")
    provider = provider or build_provider(provider_name)
    module_file = _module_file(module_name)
    source = module_file.read_text(encoding="utf-8")
    # Keep the prompt focused on the function, while coverage still measures the file.
    function_source = _function_source(module_name, function_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[GeneratedTest] = []
    seen: set[tuple] = set()
    history: list[RoundResult] = []
    feedback = Feedback()

    for iteration in range(max_rounds):
        ctx = GenerationContext(
            module_name=module_name,
            function_name=function_name,
            source=function_source,
            existing_tests="\n\n".join(item.source.strip() for item in accepted),
            iteration=iteration,
            feedback=feedback,
            use_feedback=use_feedback and iteration > 0,
            seen_keys=set(seen),
        )
        round_dir = out_dir / f"round_{iteration}"
        round_dir.mkdir(parents=True, exist_ok=True)
        prompt = render_prompt(ctx)
        prompt_path = round_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        fresh = [item for item in provider.generate(ctx) if item.key not in seen]
        if not fresh:
            break
        accepted.extend(fresh)
        seen.update(item.key for item in fresh)
        test_path = out_dir / f"test_{function_name}.py"
        write_test_module(test_path, module_name, function_name, [item.source for item in accepted])
        feedback, passed, output = run_coverage(project_root(), test_path, round_dir, module_file)
        result = RoundResult(
            iteration=iteration,
            test_count=len(accepted),
            new_tests=len(fresh),
            statement_percent=feedback.statement_percent,
            branch_percent=feedback.branch_percent,
            missing_lines=list(feedback.missing_lines),
            missing_branches=[[gap.source_line, gap.dest_line] for gap in feedback.missing_branches],
            pytest_passed=passed,
            pytest_output=output,
            prompt_path=str(prompt_path),
            test_path=str(test_path),
        )
        history.append(result)
        (round_dir / "result.json").write_text(
            json.dumps(
                {
                    "iteration": result.iteration,
                    "test_count": result.test_count,
                    "statement_percent": result.statement_percent,
                    "branch_percent": result.branch_percent,
                    "missing_lines": result.missing_lines,
                    "missing_branches": result.missing_branches,
                    "pytest_passed": result.pytest_passed,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if not passed:
            break
        if feedback.statement_percent >= target and feedback.branch_percent >= target:
            break
    (out_dir / "source_snapshot.py").write_text(source, encoding="utf-8")
    return history


def _module_file(module_name: str) -> Path:
    relative = Path(*module_name.split(".")).with_suffix(".py")
    return project_root() / "src" / relative


def _function_source(module_name: str, function_name: str) -> str:
    import importlib

    module = importlib.import_module(module_name)
    return inspect.getsource(getattr(module, function_name))
