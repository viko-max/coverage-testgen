"""Turn structured coverage gaps into the prompt a model would receive."""

from __future__ import annotations

from testgen.models import GenerationContext


def render_prompt(ctx: GenerationContext) -> str:
    feedback = _render_feedback(ctx)
    existing = ctx.existing_tests.strip() or "无"
    return (
        "你是 pytest 单元测试生成器。只输出新增测试函数，不要解释，不要重复已有用例。\n"
        "每条未覆盖语句和未覆盖分支都要有对应测试。断言必须可执行。异常路径使用 pytest.raises。\n\n"
        f"被测模块：{ctx.module_name}\n"
        f"被测函数：{ctx.function_name}\n"
        f"当前轮次：{ctx.iteration}\n\n"
        "被测源代码：\n"
        "```python\n"
        f"{ctx.source.rstrip()}\n"
        "```\n\n"
        "已有测试：\n"
        "```python\n"
        f"{existing}\n"
        "```\n\n"
        f"{feedback}\n"
    )


def _render_feedback(ctx: GenerationContext) -> str:
    if ctx.iteration == 0 or not ctx.use_feedback:
        return (
            "覆盖率反馈：本轮不提供未覆盖路径。\n"
            "请只补充一条尚未出现的可执行用例。"
        )
    fb = ctx.feedback
    lines = [
        "覆盖率反馈：请只针对下面尚未覆盖的路径补充测试。",
        f"当前语句覆盖率：{fb.statement_percent:.1f}%",
        f"当前分支覆盖率：{fb.branch_percent:.1f}%",
        "未覆盖语句：",
    ]
    if fb.missing_lines:
        for number, text in zip(fb.missing_lines, fb.missing_line_text):
            lines.append(f"- L{number}: {text}")
    else:
        lines.append("- 无")
    lines.append("未覆盖分支（源行 -> 未走到的目标行）：")
    if fb.missing_branches:
        for gap in fb.missing_branches:
            lines.append(f"- L{gap.source_line} -> L{gap.dest_line}")
    else:
        lines.append("- 无")
    return "\n".join(lines)
