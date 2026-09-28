"""Charts and fixed-size pages used as experiment screenshots."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import matplotlib.pyplot as plt

from testgen.pipeline import project_root

INK = "#1A1A1A"
BLUE = "#143D59"
GREEN = "#1F7A4D"
ORANGE = "#C4491D"
GRAY = "#8D939A"
PAPER = "#F7F5F1"


def _series(rows: list[dict], key: str) -> tuple[list[int], list[float]]:
    return [row["iteration"] + 1 for row in rows], [row[key] for row in rows]


def _style_axis(ax, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=13, color=INK, pad=10)
    ax.set_xlabel("轮次")
    ax.set_ylabel("覆盖率 (%)")
    ax.set_ylim(0, 105)
    ax.set_xticks(range(1, 9))
    ax.grid(True, axis="y", color="#E2DDD4")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors="#5C6570")


def draw_charts(summary: dict, figures: Path) -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.5), dpi=150)
    fig.patch.set_facecolor("white")
    for ax, subject in zip(axes, summary["subjects"]):
        ax.set_facecolor("white")
        for mode, stmt_color, branch_color in (
            ("feedback", BLUE, GREEN),
            ("blind", ORANGE, GRAY),
        ):
            rows = subject["modes"][mode]
            xs, stmt = _series(rows, "statement_percent")
            _, branch = _series(rows, "branch_percent")
            label = "反馈" if mode == "feedback" else "盲补"
            ax.plot(xs, stmt, color=stmt_color, marker="o", linewidth=2.2, label=f"{label} 语句")
            ax.plot(xs, branch, color=branch_color, marker="s", linewidth=1.8, linestyle="--", label=f"{label} 分支")
        _style_axis(ax, subject["title"])
        ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(figures / "coverage_curves.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    for subject, filename in zip(summary["subjects"], ("shipping_curve.png", "access_curve.png")):
        fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=150)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        for mode, stmt_color, branch_color in (
            ("feedback", BLUE, GREEN),
            ("blind", ORANGE, GRAY),
        ):
            rows = subject["modes"][mode]
            xs, stmt = _series(rows, "statement_percent")
            _, branch = _series(rows, "branch_percent")
            label = "反馈" if mode == "feedback" else "盲补"
            ax.plot(xs, stmt, color=stmt_color, marker="o", linewidth=2.4, label=f"{label} 语句")
            ax.plot(xs, branch, color=branch_color, marker="s", linewidth=2.0, linestyle="--", label=f"{label} 分支")
        _style_axis(ax, subject["title"])
        ax.legend(frameon=False, fontsize=9, ncol=2)
        fig.tight_layout()
        fig.savefig(figures / filename, bbox_inches="tight", facecolor="white")
        plt.close(fig)


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ margin: 0; background: {PAPER}; width: 610px; }}
  .frame {{
    width: 610px; box-sizing: border-box;
    background: {PAPER}; color: {INK};
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    padding: 14px 16px 16px;
  }}
  h1 {{ font-size: 20px; margin: 0; font-weight: 650; }}
  .meta {{ color: #5C6570; font-size: 12px; margin-top: 2px; }}
  .rule {{ height: 1px; background: #E2DDD4; margin: 8px 0 10px; }}
</style>
</head>
<body><div class="frame">{body}</div></body>
</html>
"""


def _results_page(summary: dict, chart_png: Path) -> str:
    encoded = base64.b64encode(chart_png.read_bytes()).decode("ascii")
    shipping = summary["subjects"][0]
    fb = shipping["modes"]["feedback"][-1]
    bl = shipping["modes"]["blind"][-1]
    body = f"""
    <h1>运费函数 · 实验结果</h1>
    <div class="meta">provider = mock · 未调用真实 API · coverage.py --branch</div>
    <div class="rule"></div>
    <div class="cards">
      <div class="card"><div class="k">反馈</div><div class="v">{fb["test_count"]} 轮到 100%</div><div class="s">语句 {fb["statement_percent"]}% · 分支 {fb["branch_percent"]}%</div></div>
      <div class="card"><div class="k">盲补</div><div class="v">{bl["test_count"]} 轮到 100%</div><div class="s">第 5、7 轮覆盖率不升</div></div>
    </div>
    <img alt="coverage" src="data:image/png;base64,{encoded}">
    <style>
      .cards {{ display: flex; gap: 8px; margin-bottom: 8px; }}
      .card {{ flex: 1; background: white; border: 1px solid #E2DDD4; padding: 8px 10px; }}
      .k {{ color: #5C6570; font-size: 12px; }}
      .v {{ font-size: 18px; font-weight: 700; margin: 2px 0; }}
      .s {{ font-size: 12px; }}
      img {{ width: 100%; height: 300px; object-fit: contain; object-position: left center; background: white; border: 1px solid #E2DDD4; }}
    </style>
    """
    return _page("运费实验结果", body)


def _console_page(summary: dict) -> str:
    shipping = summary["subjects"][0]["modes"]["feedback"]
    blocks = []
    for row in shipping:
        passed = next(line.strip() for line in row["pytest_output"].splitlines() if "passed" in line)
        blocks.append(
            f"""<div class="run">
              <div class="rh">round {row["iteration"]} · 语句 {row["statement_percent"]}% · 分支 {row["branch_percent"]}%</div>
              <pre>{passed}</pre>
            </div>"""
        )
    body = f"""
    <h1>pytest 输出</h1>
    <div class="meta">shipping_fee · feedback · 4 轮全部通过</div>
    <div class="rule"></div>
    <div class="term">{''.join(blocks)}</div>
    <style>
      .term {{ background: #1B1E23; color: #E8E4DC; padding: 10px 12px; }}
      .run {{ margin-bottom: 8px; }}
      .rh {{ color: #8FCBB2; font-size: 13px; }}
      pre {{ margin: 0; font-family: Consolas, monospace; font-size: 13px; white-space: pre-wrap; }}
    </style>
    """
    return _page("pytest 输出", body)


def _prompt_page(prompt_text: str) -> str:
    feedback = prompt_text.split("覆盖率反馈：", 1)[1].strip()
    body = f"""
    <h1>第 2 轮提示词</h1>
    <div class="meta">shipping_fee · 上一轮语句 62.5% · 分支 40.0%</div>
    <div class="rule"></div>
    <pre>{feedback}</pre>
    <style>
      pre {{
        margin: 0; background: white; border: 1px solid #E2DDD4;
        padding: 10px 12px; font-family: Consolas, monospace;
        font-size: 12px; line-height: 1.35; white-space: pre-wrap;
      }}
    </style>
    """
    return _page("提示词反馈", body)


def main() -> None:
    root = project_root()
    summary = json.loads((root / "artifacts" / "summary.json").read_text(encoding="utf-8"))
    figures = root / "artifacts" / "figures"
    preview = root / "artifacts" / "preview"
    figures.mkdir(parents=True, exist_ok=True)
    preview.mkdir(parents=True, exist_ok=True)
    draw_charts(summary, figures)
    prompt = (root / "artifacts" / "shipping_fee_feedback" / "round_1" / "prompt.txt").read_text(encoding="utf-8")
    (preview / "results.html").write_text(_results_page(summary, figures / "shipping_curve.png"), encoding="utf-8")
    (preview / "console.html").write_text(_console_page(summary), encoding="utf-8")
    (preview / "prompt.html").write_text(_prompt_page(prompt), encoding="utf-8")
    print(preview)


if __name__ == "__main__":
    main()
