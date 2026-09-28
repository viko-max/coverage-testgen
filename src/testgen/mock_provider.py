"""Coverage-guided stand-in for an LLM.

It proposes concrete inputs by solving the function's branch conditions, executes
them locally, and picks the next test from the uncovered lines the pipeline
passes in. The selection uses the same GenerationContext a real model would see.
"""

from __future__ import annotations

import ast
import importlib
import operator
import sys
from dataclasses import dataclass, field

from testgen.models import GeneratedTest, GenerationContext

_OPS = {
    "Lt": operator.lt,
    "LtE": operator.le,
    "Gt": operator.gt,
    "GtE": operator.ge,
    "Eq": operator.eq,
    "NotEq": operator.ne,
}


@dataclass
class Constraint:
    name: str
    kind: str
    pred: object
    hints: list


@dataclass
class State:
    values: dict = field(default_factory=dict)
    preds: dict = field(default_factory=dict)

    def apply(self, conjunction: list[Constraint], pools: Pools) -> State | None:
        values = dict(self.values)
        preds = {key: list(value) for key, value in self.preds.items()}
        for constraint in conjunction:
            preds.setdefault(constraint.name, []).append(constraint)
            chosen = pick_value(constraint.name, preds[constraint.name], pools, values.get(constraint.name))
            if chosen is None:
                return None
            values[constraint.name] = chosen
        return State(values, preds)


@dataclass
class Pools:
    numbers: list
    strings: list


@dataclass
class Candidate:
    args: dict
    lines: set[int]
    result: object
    exc_type: str | None

    @property
    def key(self) -> tuple:
        return tuple((name, _norm(value)) for name, value in self.args.items())


def _norm(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class MockProvider:
    def __init__(self):
        self._cache: dict[tuple[str, str], list[Candidate]] = {}

    def generate(self, ctx: GenerationContext) -> list[GeneratedTest]:
        candidates = [item for item in self._candidates(ctx) if item.key not in ctx.seen_keys]
        if not candidates:
            return []
        ordered = sorted(candidates, key=lambda item: (len(item.lines), item.key))
        if ctx.iteration == 0:
            non_raising = [item for item in ordered if item.exc_type is None]
            chosen = (non_raising or ordered)[0]
        elif not ctx.use_feedback:
            chosen = ordered[0]
        else:
            ranked = sorted(candidates, key=lambda item: _score(item, ctx), reverse=True)
            if _score(ranked[0], ctx) <= 0:
                return []
            chosen = ranked[0]
        source = _render(ctx.function_name, chosen, ctx.iteration)
        return [GeneratedTest(name=f"test_iter{ctx.iteration}_1_{ctx.function_name}", source=source, key=chosen.key)]

    def _candidates(self, ctx: GenerationContext) -> list[Candidate]:
        cache_key = (ctx.module_name, ctx.function_name)
        if cache_key not in self._cache:
            module = importlib.import_module(ctx.module_name)
            function = getattr(module, ctx.function_name)
            tree = ast.parse(ctx.source)
            func_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == ctx.function_name)
            self._cache[cache_key] = _enumerate(function, func_node)
        return self._cache[cache_key]


def _score(candidate: Candidate, ctx: GenerationContext) -> int:
    missing = set(ctx.feedback.missing_lines)
    line_hits = len(candidate.lines & missing)
    branch_hits = 0
    for gap in ctx.feedback.missing_branches:
        if gap.dest_line in candidate.lines:
            branch_hits += 1
        elif gap.dest_line <= 0 and gap.source_line in candidate.lines:
            branch_hits += 1
    return line_hits * 2 + branch_hits


def _enumerate(function, func_node: ast.FunctionDef) -> list[Candidate]:
    param_names = [arg.arg for arg in func_node.args.args]
    annotations = {arg.arg: _ann_name(arg.annotation) for arg in func_node.args.args}
    pools = Pools(numbers=_number_pool(func_node), strings=_string_pool(func_node))
    found: list[dict] = []

    def walk(stmts: list[ast.stmt], state: State) -> None:
        index = 0
        while index < len(stmts):
            stmt = stmts[index]
            if isinstance(stmt, ast.If):
                for want in (True, False):
                    for conjunction in _dnf(stmt.test, want):
                        new_state = state.apply(conjunction, pools)
                        if new_state is None:
                            continue
                        branch = stmt.body if want else stmt.orelse
                        if _always_exits(branch):
                            walk(branch, new_state)
                        else:
                            walk(list(branch) + list(stmts[index + 1 :]), new_state)
                return
            if isinstance(stmt, (ast.Return, ast.Raise)):
                found.append(dict(state.values))
                return
            index += 1
        found.append(dict(state.values))

    walk(func_node.body, State())
    unique: list[Candidate] = []
    seen = set()
    for values in found:
        args = _fill(values, param_names, annotations, pools)
        key = tuple((name, _norm(args[name])) for name in param_names)
        if key in seen:
            continue
        seen.add(key)
        ordered = {name: args[name] for name in param_names}
        lines, result, exc_type = _trace(function, [ordered[name] for name in param_names])
        unique.append(Candidate(args=ordered, lines=lines, result=result, exc_type=exc_type))
    return unique


def _fill(values: dict, names: list[str], annotations: dict, pools: Pools) -> dict:
    filled = {}
    for name in names:
        if name in values:
            filled[name] = values[name]
            continue
        kind = annotations.get(name)
        if kind == "bool":
            filled[name] = False
        elif kind == "str":
            filled[name] = "other"
        else:
            filled[name] = 5
    return filled


def _trace(function, args: list):
    lines: set[int] = set()
    code = function.__code__

    def tracer(frame, event, arg):
        if event == "line" and frame.f_code is code:
            lines.add(frame.f_lineno)
        return tracer

    result = None
    exc_type = None
    sys.settrace(tracer)
    try:
        result = function(*args)
    except Exception as exc:
        exc_type = type(exc).__name__
    finally:
        sys.settrace(None)
    return lines, result, exc_type


def _always_exits(stmts: list[ast.stmt]) -> bool:
    if not stmts:
        return False
    for stmt in stmts:
        if isinstance(stmt, (ast.Return, ast.Raise)):
            return True
        if isinstance(stmt, ast.If) and _always_exits(stmt.body) and _always_exits(stmt.orelse):
            return True
    return False


def _dnf(node: ast.expr, want_true: bool) -> list[list[Constraint]]:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _dnf(node.operand, not want_true)
    if isinstance(node, ast.Name):
        if want_true:
            return [[Constraint(node.id, "bool", lambda value: bool(value), [True])]]
        return [[Constraint(node.id, "bool", lambda value: not bool(value), [False])]]
    if isinstance(node, ast.Compare):
        return _dnf_compare(node, want_true)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        if want_true:
            return _cartesian([_dnf(value, True) for value in node.values])
        choices: list[list[Constraint]] = []
        for value in node.values:
            choices.extend(_dnf(value, False))
        return choices
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        if want_true:
            choices = []
            for value in node.values:
                choices.extend(_dnf(value, True))
            return choices
        return _cartesian([_dnf(value, False) for value in node.values])
    return []


def _dnf_compare(node: ast.Compare, want_true: bool) -> list[list[Constraint]]:
    if len(node.ops) != 1 or not isinstance(node.left, ast.Name):
        return []
    right = node.comparators[0]
    if not isinstance(right, ast.Constant):
        return []
    op_name = type(node.ops[0]).__name__
    const = right.value
    op = _OPS[op_name]

    def holds(value, op=op, const=const):
        try:
            return bool(op(value, const))
        except TypeError:
            return False

    if want_true:
        pred = holds
        hint = _hint(op_name, const, True)
    else:
        pred = lambda value, holds=holds: not holds(value)
        hint = _hint(op_name, const, False)
    kind = "str" if isinstance(const, str) else "num"
    return [[Constraint(node.left.id, kind, pred, [hint])]]


def _hint(op_name: str, const, want_true: bool):
    if isinstance(const, str):
        if (op_name == "Eq" and want_true) or (op_name == "NotEq" and not want_true):
            return const
        return "other"
    step = {
        ("Lt", True): const - 1,
        ("Lt", False): const,
        ("LtE", True): const,
        ("LtE", False): const + 1,
        ("Gt", True): const + 1,
        ("Gt", False): const,
        ("GtE", True): const,
        ("GtE", False): const - 1,
        ("Eq", True): const,
        ("Eq", False): const + 1,
        ("NotEq", True): const + 1,
        ("NotEq", False): const,
    }[(op_name, want_true)]
    if isinstance(step, float) and step.is_integer():
        return int(step)
    return step


def _cartesian(parts: list[list[list[Constraint]]]) -> list[list[Constraint]]:
    if not parts or any(not part for part in parts):
        return []
    combined: list[list[Constraint]] = [[]]
    for part in parts:
        combined = [left + right for left in combined for right in part]
    return combined


def pick_value(name: str, constraints: list[Constraint], pools: Pools, current):
    preds = [item.pred for item in constraints]
    hints = [hint for item in constraints for hint in item.hints]
    kind = constraints[-1].kind
    if kind == "bool":
        pool = [True, False]
    elif kind == "str":
        pool = list(dict.fromkeys([*hints, *pools.strings, "other"]))
    else:
        pool = list(dict.fromkeys([*hints, *pools.numbers]))
    if current is not None:
        try:
            if all(pred(current) for pred in preds):
                return current
        except TypeError:
            pass
    for value in pool:
        try:
            if all(pred(value) for pred in preds):
                return value
        except TypeError:
            continue
    return None


def _number_pool(func_node: ast.FunctionDef) -> list:
    nums = {-1, 0, 1, 5, 10, 11}
    for node in ast.walk(func_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            nums.add(node.value)
            nums.add(node.value - 1)
            nums.add(node.value + 1)
    return sorted(nums, key=lambda item: (abs(item - 5), item))


def _string_pool(func_node: ast.FunctionDef) -> list[str]:
    found = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isidentifier():
            found.append(node.value)
    return list(dict.fromkeys(found))


def _ann_name(annotation: ast.expr | None) -> str:
    if isinstance(annotation, ast.Name):
        return annotation.id
    return ""


def _render(function_name: str, candidate: Candidate, iteration: int) -> str:
    args = ", ".join(repr(_norm(candidate.args[name])) for name in candidate.args)
    name = f"test_iter{iteration}_1_{function_name}"
    if candidate.exc_type:
        return (
            f"def {name}():\n"
            f"    with pytest.raises({candidate.exc_type}):\n"
            f"        {function_name}({args})\n"
        )
    return f"def {name}():\n    assert {function_name}({args}) == {candidate.result!r}\n"
