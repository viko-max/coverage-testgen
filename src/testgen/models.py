"""Shared data passed between the prompt, the model adapter, and the runner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BranchGap:
    source_line: int
    dest_line: int


@dataclass
class Feedback:
    statement_percent: float = 0.0
    branch_percent: float = 0.0
    missing_lines: list[int] = field(default_factory=list)
    missing_line_text: list[str] = field(default_factory=list)
    missing_branches: list[BranchGap] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.missing_lines and not self.missing_branches


@dataclass(frozen=True)
class GeneratedTest:
    name: str
    source: str
    key: tuple


@dataclass
class GenerationContext:
    module_name: str
    function_name: str
    source: str
    existing_tests: str
    iteration: int
    feedback: Feedback
    use_feedback: bool
    seen_keys: set[tuple] = field(default_factory=set)


@dataclass
class RoundResult:
    iteration: int
    test_count: int
    new_tests: int
    statement_percent: float
    branch_percent: float
    missing_lines: list[int]
    missing_branches: list[list[int]]
    pytest_passed: bool
    pytest_output: str
    prompt_path: str
    test_path: str
