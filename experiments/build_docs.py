"""Build the lab report and the 12-slide deck from artifacts/summary.json."""

from __future__ import annotations

import json
from pathlib import Path

import coverage
import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from pptx import Presentation
from pptx.dml.color import RGBColor as PptColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn as ppt_qn
from pptx.util import Emu, Inches, Pt as PptPt

from testgen.pipeline import project_root

BLUE = "143D59"
INK = "1A1A1A"
MUTED = "5C6570"
PAPER = "F7F5F1"
ORANGE = "C4491D"


def _font(run, name: str, size: float, bold: bool = False, color: str | None = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)


def _p(doc: Document, text: str, size: float = 12, bold: bool = False, space_after: float = 8, center: bool = False):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(space_after)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.25
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    _font(run, "宋体", size, bold)
    return paragraph


def _h(doc: Document, text: str, level: int) -> None:
    paragraph = doc.add_heading(text, level=level)
    for run in paragraph.runs:
        _font(run, "黑体", 16 if level == 1 else 14, True, BLUE)


def _table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        run = cell.paragraphs[0].add_run(header)
        _font(run, "黑体", 10.5, True, "FFFFFF")
        _shade(cell, BLUE)
    for r_index, row in enumerate(rows):
        for c_index, value in enumerate(row):
            cell = table.rows[r_index + 1].cells[c_index]
            cell.text = ""
            run = cell.paragraphs[0].add_run(value)
            _font(run, "宋体", 10.5)
            if r_index % 2 == 1:
                _shade(cell, "F4F1EA")
    doc.add_paragraph()


def _pic(doc: Document, path: Path, width: float = 15.2) -> None:
    if path.exists():
        doc.add_picture(str(path), width=Cm(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _rounds(rows: list[dict]) -> list[list[str]]:
    return [
        [
            str(row["iteration"] + 1),
            str(row["test_count"]),
            f"{row['statement_percent']}",
            f"{row['branch_percent']}",
            "通过" if row["pytest_passed"] else "失败",
            str(len(row["missing_lines"])),
        ]
        for row in rows
    ]


def build_docx(root: Path, summary: dict) -> Path:
    shipping, access = summary["subjects"]
    sf, sb = shipping["modes"]["feedback"], shipping["modes"]["blind"]
    af, ab = access["modes"]["feedback"], access["modes"]["blind"]
    figures = root / "artifacts" / "figures"
    shots = figures / "shots"
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.4)
        section.bottom_margin = Cm(2.4)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)
    _p(doc, "课程大作业实验报告", 14, True, 6, True)
    _p(doc, "基于大模型与代码覆盖率反馈的迭代式单元测试自动生成", 18, True, 10, True)
    _p(doc, "姓名：____________    学号：____________", 12, False, 4, True)
    _p(doc, "2026年9月28日", 12, False, 16, True)
    _h(doc, "摘要", 1)
    _p(
        doc,
        "手写单元测试费时，而且人容易只写到正常路径。本系统把被测函数源码交给生成器产出 pytest，再用 coverage.py 同时收集语句覆盖率和分支覆盖率。没走到的语句和分支写回下一轮提示词，生成器只补这些缺口。本次实验按要求使用项目内虚拟环境，生成器为 mock，没有读取或发送任何 API key。对照实验把同一候选池改成不看缺口、按路径从短到长追加。运费函数在反馈模式下 4 轮达到语句 100% 和分支 100%，盲补用了 8 轮。门禁函数分别是 7 轮和 8 轮，反馈在中段拉开差距。",
    )
    _h(doc, "1  问题", 1)
    _p(
        doc,
        "传统单测的成本不在框架，在用例本身。一个带地区、重量和会员折扣的计费函数，正常路径几分钟能写完，重量小于等于 0、偏远地区加超重再加会员，这些组合就容易漏。漏了以后语句覆盖率看起来还不低，因为 if 那一行已经执行过，另一侧分支却没进去。",
    )
    _p(
        doc,
        "所以问题不是再写一个能生成测试的脚本，而是让生成过程看见覆盖率。每轮只告诉生成器还缺哪几行、哪个分支没走到，避免它反复交回同一类正常路径。",
    )
    _h(doc, "2  系统做法", 1)
    _p(doc, "输入是被测函数源码。输出是一份可直接运行的 pytest 文件，外加每一轮的提示词、coverage json 和覆盖率。循环如下。")
    _p(doc, "1. 读取函数源码，拼出提示词。第 1 轮不提供缺口，只要求一条可执行用例。")
    _p(doc, "2. 生成器返回新增测试函数。测试文件按轮累加，不覆盖旧用例。")
    _p(doc, "3. 在虚拟环境里执行 coverage run --branch -m pytest，只统计 subjects 包。")
    _p(doc, "4. 从 coverage json 读出该源文件的未覆盖语句和未覆盖分支，连同当前覆盖率写进下一轮提示词。")
    _p(doc, "5. 语句覆盖率和分支覆盖率都达到 100%，或到达轮次上限，就停止。")
    _p(
        doc,
        "语句和分支一起看，是因为只看语句会把“条件行已执行”当成“两侧都走过”。提示词里两种缺口都列出来，生成器才能补 else、异常和组合条件。",
    )
    _p(
        doc,
        "生成器做成可替换接口。mock 与 OpenAI 兼容适配器接收同一份 GenerationContext。适配器在 LLM_API_KEY 为空时直接拒绝，命令行也禁止切到 openai。这次实验因此不会发生网络请求。mock 的做法是：根据比较条件构造能走进各分支的参数，实际调用函数记录走到的行，第 1 轮取最短的正常路径，之后若开启反馈，就选能盖住最多未覆盖行的那条。期望值来自这次调用，所以断言锁住的是当前实现，函数里若有缺陷，测试会把缺陷一起记下来。这一点在讨论里单独说明。",
    )
    _h(doc, "3  实验设置", 1)
    _p(
        doc,
        f"环境：Python {__import__('sys').version.split()[0]}，pytest {pytest.__version__}，coverage.py {coverage.__version__}，虚拟环境位于项目目录 .venv。两个被测函数都只依赖标准库。运费函数 shipping_fee 有 16 条语句、10 个分支，按重量、地区和会员计算费用，非法重量抛出 ValueError。门禁函数 access_decision 有 14 条语句、12 个分支，按角色、小时和是否紧急返回 allow、limited 或 deny。",
    )
    _p(
        doc,
        "每种函数跑两种模式，轮次上限 8。反馈模式从第 2 轮起把未覆盖语句和未覆盖分支写入提示词。盲补模式使用同一个候选池和同一条第 1 轮用例，之后不看缺口，只按执行行数从少到多追加。两边的差别只在选题依据，不在生成能力。",
    )
    _h(doc, "4  实验结果", 1)
    _p(doc, "4.1  运费函数", 2)
    _p(
        doc,
        f"反馈模式第 {sf[-1]['test_count']} 轮达到语句 {sf[-1]['statement_percent']}% 、分支 {sf[-1]['branch_percent']}%，pytest 全部通过。盲补模式第 {sb[-1]['test_count']} 轮才到达同一终点。第 1 轮两边相同，都是 shipping_fee(1, 'remote', False)，语句 62.5%，分支 40.0%。",
    )
    _table(doc, ["轮次", "用例数", "语句%", "分支%", "pytest", "未覆盖语句数"], _rounds(sf))
    _p(doc, "表 1  运费函数，反馈模式。", 10.5, False, 12)
    _table(doc, ["轮次", "用例数", "语句%", "分支%", "pytest", "未覆盖语句数"], _rounds(sb))
    _p(doc, "表 2  运费函数，盲补模式。盲补第 5 轮和第 7 轮覆盖率没有上升。", 10.5, False, 12)
    _pic(doc, figures / "coverage_curves.png")
    _p(doc, "图 1  两个函数的语句覆盖率与分支覆盖率。实线为语句，虚线为分支。", 10.5, False, 12)
    _p(doc, "4.2  反馈补到了哪里", 2)
    _p(
        doc,
        "第 1 轮只走进偏远地区、重量不超过 10、非会员。提示词因此列出未覆盖语句：非法重量的 raise、本地价、其他地区价、超重附加费、会员九折。第 2 轮生成 shipping_fee(11, 'local', True)。这一条同时补上本地价、超重和会员折扣，语句覆盖率从 62.5% 升到 87.5%，分支从 40.0% 升到 80.0%。第 3 轮补 weight <= 0 的异常。第 4 轮用 shipping_fee(11, 'other', True) 补上其他地区，两种覆盖率都到 100%。",
    )
    _p(
        doc,
        "盲补没有这份清单。它第 5 轮新增 shipping_fee(11, 'remote', True)。超重和会员折扣在前面已经分别走过，这条只是把旧路径再组合一次，语句覆盖率停在 81.2%，分支停在 70.0%。第 7 轮 shipping_fee(1, 'local', True) 同样没有新语句，停在 93.8% 和 90.0%，直到第 8 轮才走进其他地区。",
    )
    _p(doc, "4.3  门禁函数", 2)
    mid_f = next(row for row in af if row["test_count"] == 4)
    mid_b = next(row for row in ab if row["test_count"] == 4)
    _p(
        doc,
        f"反馈模式 {af[-1]['test_count']} 轮达到 100%，盲补 {ab[-1]['test_count']} 轮达到 100%。终点接近，中段不同。各写完 4 条用例时，反馈的语句覆盖率是 {mid_f['statement_percent']}%，分支 {mid_f['branch_percent']}%；盲补是 {mid_b['statement_percent']}% 和 {mid_b['branch_percent']}%。反馈优先补还能盖住缺口的角色、时段和紧急标志，盲补会先碰到覆盖行数更少、但对剩余缺口帮助有限的路径。",
    )
    _table(doc, ["轮次", "用例数", "语句%", "分支%", "pytest", "未覆盖语句数"], _rounds(af))
    _p(doc, "表 3  门禁函数，反馈模式。", 10.5, False, 8)
    _table(doc, ["轮次", "用例数", "语句%", "分支%", "pytest", "未覆盖语句数"], _rounds(ab))
    _p(doc, "表 4  门禁函数，盲补模式。", 10.5, False, 12)
    _h(doc, "5  实验截图", 1)
    _p(doc, "下面三张图是实验结果页面、pytest 控制台和写回提示词的缺口列表，数据与 artifacts/summary.json 一致。")
    _pic(doc, shots / "results.png")
    _p(doc, "图 2  两种模式到达 100% 所用轮次，以及覆盖率曲线。", 10.5)
    _pic(doc, shots / "console.png")
    _p(doc, "图 3  运费函数反馈模式每一轮的 pytest 结果，4 轮全部通过。", 10.5)
    _pic(doc, shots / "prompt.png")
    _p(doc, "图 4  第 2 轮提示词。上一轮的未覆盖语句和未覆盖分支被写进提示词。", 10.5)
    _h(doc, "6  讨论", 1)
    _p(
        doc,
        "这组对照说明差距来自反馈，不来自生成器突然变强。两边第 1 轮用例相同，候选池相同。盲补也会慢慢到 100%，因为池子本身能覆盖这些纯比较分支。它多花的轮次，花在已经盖住的组合上。反馈把未覆盖行交给选题，一条用例可以同时打中多个缺口。",
    )
    _p(
        doc,
        "本次没有调用大模型。mock 会求解比较条件，提案质量高于一个会写错断言的在线模型。真实模型接入后，循环不用改：无效用例留在文件里，下一轮仍然只看到还没覆盖的行。命令行在 provider 不是 mock 时直接退出，避免实验机器误用密钥。",
    )
    _p(
        doc,
        "断言的期望值来自执行被测函数。这能保证生成的测试现在是绿的，但不能发现函数本身算错。若课程后续要求独立预期，应把规格写成单独的判定，而不是再调用被测函数。另外两个样例都没有循环、I/O 和全局状态，覆盖率曲线不能直接外推到带外部依赖的业务代码。",
    )
    _h(doc, "7  结论", 1)
    _p(
        doc,
        "把未覆盖语句和未覆盖分支写回提示词，可以让迭代生成少做无效补充。在本次虚拟环境、mock 生成器、不调用真实 API 的条件下，运费函数 4 轮达到语句与分支双 100%，盲补需要 8 轮，并且中间出现两轮覆盖率完全不升。门禁函数的终点只差 1 轮，但写完 4 条用例时反馈已经明显高于盲补。系统留下了与 mock 相同的提示词接口，后续换在线模型时，pytest 和 coverage 这两段不用重写。",
    )
    _h(doc, "附录 A  反馈模式最终用例", 1)
    for relative in (
        "artifacts/shipping_fee_feedback/test_shipping_fee.py",
        "artifacts/access_decision_feedback/test_access_decision.py",
    ):
        _p(doc, relative, 10.5, True, 4)
        for line in (root / relative).read_text(encoding="utf-8").splitlines():
            _p(doc, line if line else " ", 9, False, 0)
        doc.add_paragraph()
    _h(doc, "附录 B  复现", 1)
    _p(doc, "py -3 -m venv .venv")
    _p(doc, ".\\.venv\\Scripts\\python -m pip install -e \".[report]\"")
    _p(doc, ".\\.venv\\Scripts\\python -m pytest")
    _p(doc, ".\\.venv\\Scripts\\python experiments\\run_experiment.py")
    out = root / "docs" / "实验报告.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def _set_run(run, name: str, size: int, color: str, bold: bool = False) -> None:
    run.font.size = PptPt(size)
    run.font.bold = bold
    run.font.color.rgb = PptColor.from_string(color)
    run.font.name = name
    r_pr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        element = r_pr.find(ppt_qn(tag))
        if element is None:
            element = r_pr.makeelement(ppt_qn(tag))
            r_pr.append(element)
        element.set("typeface", name)


def _blank(prs: Presentation, dark: bool = False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = PptColor.from_string("143D59" if dark else PAPER)
    return slide


def _text(slide, text: str, x, y, w, h, size: int, color: str, bold: bool = False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    _set_run(run, "微软雅黑", size, color, bold)
    return box


def _bullets(slide, items: list[str], x, y, w, h, size: int = 20, color: str = INK) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = PP_ALIGN.LEFT
        paragraph.space_after = PptPt(10)
        run = paragraph.add_run()
        run.text = item
        _set_run(run, "微软雅黑", size, color, False)


def _footer(slide, page: int, dark: bool = False) -> None:
    color = "D5DDE4" if dark else MUTED
    _text(slide, f"{page:02d}  /  12", 11.4, 7.05, 1.5, 0.3, 12, color, align=PP_ALIGN.RIGHT)


def _title(slide, text: str) -> None:
    _text(slide, text, 0.55, 0.32, 12, 0.55, 28, BLUE, True)
    shape = slide.shapes.add_shape(1, Inches(0.55), Inches(0.98), Inches(1.1), Emu(28000))
    shape.fill.solid()
    shape.fill.fore_color.rgb = PptColor.from_string(ORANGE)
    shape.line.fill.background()


def build_pptx(root: Path, summary: dict) -> Path:
    shipping, access = summary["subjects"]
    sf, sb = shipping["modes"]["feedback"], shipping["modes"]["blind"]
    af, ab = access["modes"]["feedback"], access["modes"]["blind"]
    mid_f = next(row for row in af if row["test_count"] == 4)
    mid_b = next(row for row in ab if row["test_count"] == 4)
    figures = root / "artifacts" / "figures"
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "基于覆盖率反馈的迭代式单元测试生成"

    slide = _blank(prs, dark=True)
    _text(slide, "课程大作业", 0.7, 1.55, 10, 0.4, 18, "D5DDE4")
    _text(slide, "基于覆盖率反馈的\n迭代式单元测试生成", 0.7, 2.05, 11, 1.8, 40, "FFFFFF", True)
    _text(slide, "语句覆盖率  +  分支覆盖率  →  写回下一轮提示词", 0.7, 4.35, 11, 0.4, 18, "F0D7C8")
    _text(slide, "本次实验：项目虚拟环境  ·  mock 生成器  ·  不调用真实 API", 0.7, 5.7, 10, 0.4, 16, "D5DDE4")
    _text(slide, "姓名 ________    学号 ________", 0.7, 6.3, 8, 0.35, 16, "FFFFFF")
    _footer(slide, 1, dark=True)

    slide = _blank(prs)
    _title(slide, "手写单测为什么盖不住")
    _bullets(
        slide,
        [
            "正常路径好写，异常、边界和组合路径靠人记。",
            "if 那一行执行过，不代表两个分支都走过。",
            "覆盖率要跑完才知道，补哪一条用例仍然靠人盯。",
            "一次生成若只看见源码，很容易反复交回同一类用例。",
        ],
        0.7,
        1.45,
        11.5,
        4.5,
        24,
    )
    _footer(slide, 2)

    slide = _blank(prs)
    _title(slide, "系统每一轮做什么")
    _bullets(
        slide,
        [
            "输入：被测函数源码。输出：累加的 pytest 文件。",
            "第 1 轮不给缺口，只要一条能跑的正常路径。",
            "coverage run --branch 收集语句覆盖率和分支覆盖率。",
            "未覆盖语句、未覆盖分支写进下一轮提示词。",
            "两种覆盖率都到 100%，或到达 8 轮上限，停止。",
        ],
        0.7,
        1.4,
        12,
        5,
        24,
    )
    _footer(slide, 3)

    slide = _blank(prs)
    _title(slide, "闭环")
    steps = [
        ("1  源码", "函数原文进入提示词"),
        ("2  生成", "只新增一条 pytest"),
        ("3  执行", "pytest + 分支覆盖率"),
        ("4  缺口", "未覆盖行和分支"),
        ("5  回写", "缺口进入下一轮提示词"),
    ]
    for index, (head, body) in enumerate(steps):
        left = 0.45 + index * 2.55
        shape = slide.shapes.add_shape(1, Inches(left), Inches(2.3), Inches(2.35), Inches(2.3))
        shape.fill.solid()
        shape.fill.fore_color.rgb = PptColor.from_string("FFFFFF")
        shape.line.color.rgb = PptColor.from_string("E2DDD4")
        _text(slide, head, left + 0.12, 2.48, 2.1, 0.5, 18, BLUE, True)
        _text(slide, body, left + 0.12, 3.15, 2.1, 1.0, 14, INK)
    _text(slide, "生成器可替换。实验固定为 mock，真实适配器没有密钥会直接拒绝。", 0.55, 5.3, 12, 0.6, 18, MUTED)
    _footer(slide, 4)

    slide = _blank(prs)
    _title(slide, "缺口在提示词里长这样")
    _text(slide, "运费函数第 1 轮之后，写给第 2 轮的反馈", 0.7, 1.3, 10, 0.4, 16, MUTED)
    card = slide.shapes.add_shape(1, Inches(0.7), Inches(1.85), Inches(11.8), Inches(4.5))
    card.fill.solid()
    card.fill.fore_color.rgb = PptColor.from_string("FFFFFF")
    card.line.color.rgb = PptColor.from_string("E2DDD4")
    _bullets(
        slide,
        [
            "当前语句覆盖率 62.5%    当前分支覆盖率 40.0%",
            "未覆盖语句：非法重量、本地价、其他地区、超重、会员九折",
            "未覆盖分支：L7→L8，L9→L11，L11→L14，L15→L16，L20→L21",
            "要求：只补这些路径，不重复已有用例",
        ],
        0.95,
        2.1,
        11.2,
        3.8,
        22,
    )
    _footer(slide, 5)

    slide = _blank(prs)
    _title(slide, "对照只改一件事")
    _bullets(
        slide,
        [
            "反馈：下一轮挑选能盖住最多未覆盖行的输入。",
            "盲补：同一候选池，按执行行数从少到多追加，不看缺口。",
            "第 1 轮相同：shipping_fee(1, 'remote', False)。",
            "因此曲线差距来自要不要把缺口写回提示词。",
        ],
        0.7,
        1.45,
        12,
        4.6,
        24,
    )
    _footer(slide, 6)

    slide = _blank(prs)
    _title(slide, "两个被测函数")
    _bullets(
        slide,
        [
            "shipping_fee：16 条语句，10 个分支。重量、地区、会员，非法重量抛错。",
            "access_decision：14 条语句，12 个分支。角色、小时、紧急标志。",
            "虚拟环境 .venv，Python 3.13，pytest 9.1，coverage.py 7.16。",
            "只测 subjects 包。每轮保留提示词、pytest 输出和 coverage json。",
        ],
        0.7,
        1.45,
        12,
        4.6,
        24,
    )
    _footer(slide, 7)

    slide = _blank(prs)
    _title(slide, "运费：4 轮对 8 轮")
    slide.shapes.add_picture(str(figures / "shipping_curve.png"), Inches(0.45), Inches(1.25), Inches(8.3), Inches(5.4))
    _text(slide, "反馈", 9.0, 1.8, 3.8, 0.4, 16, MUTED)
    _text(slide, "4 轮到 100%", 9.0, 2.2, 3.8, 0.7, 28, BLUE, True)
    _text(slide, f"语句 {sf[-1]['statement_percent']}%\n分支 {sf[-1]['branch_percent']}%", 9.0, 3.05, 3.8, 0.9, 18, INK)
    _text(slide, "盲补", 9.0, 4.2, 3.8, 0.4, 16, MUTED)
    _text(slide, "8 轮到 100%", 9.0, 4.6, 3.8, 0.7, 28, ORANGE, True)
    _text(slide, "第 5、7 轮覆盖率不升", 9.0, 5.45, 3.8, 0.7, 16, INK)
    _footer(slide, 8)

    slide = _blank(prs)
    _title(slide, "同样一轮，补的不是一回事")
    _bullets(
        slide,
        [
            "反馈第 2 轮：shipping_fee(11, 'local', True)",
            "一条同时盖住本地价、超重、会员九折。62.5% / 40% → 87.5% / 80%。",
            "随后两轮补异常重量和其他地区，第 4 轮双 100%。",
            "盲补第 5 轮：shipping_fee(11, 'remote', True)",
            "超重和折扣已经分别走过，覆盖率停在 81.2% / 70.0%。",
        ],
        0.7,
        1.4,
        12,
        5.2,
        22,
    )
    _footer(slide, 9)

    slide = _blank(prs)
    _title(slide, "门禁：终点接近，中段分开")
    slide.shapes.add_picture(str(figures / "access_curve.png"), Inches(0.45), Inches(1.25), Inches(8.3), Inches(5.4))
    _text(slide, "写完 4 条用例时", 9.0, 1.7, 3.9, 0.4, 16, MUTED)
    _text(slide, f"{mid_f['statement_percent']}% / {mid_f['branch_percent']}%", 9.0, 2.2, 3.9, 0.6, 26, BLUE, True)
    _text(slide, "反馈  语句 / 分支", 9.0, 2.9, 3.9, 0.4, 16, INK)
    _text(slide, f"{mid_b['statement_percent']}% / {mid_b['branch_percent']}%", 9.0, 3.6, 3.9, 0.6, 26, ORANGE, True)
    _text(slide, "盲补  语句 / 分支", 9.0, 4.3, 3.9, 0.4, 16, INK)
    _text(slide, f"终点  {af[-1]['test_count']} 轮  vs  {ab[-1]['test_count']} 轮", 9.0, 5.2, 3.9, 0.8, 18, INK)
    _footer(slide, 10)

    slide = _blank(prs)
    _title(slide, "这组数字不能被说成什么")
    _bullets(
        slide,
        [
            "没有调用在线大模型。mock 能按比较条件构造输入。",
            "期望值来自执行被测函数，测的是现有行为，发现不了算错。",
            "样例没有循环和外部依赖，不能直接外推到业务工程。",
            "盲补最终也能到 100%，它只是把轮次花在重复组合上。",
            "换真实模型时保留这段循环：无效用例留下，缺口继续回写。",
        ],
        0.7,
        1.4,
        12,
        5.2,
        22,
    )
    _footer(slide, 11)

    slide = _blank(prs)
    _title(slide, "结论")
    _text(slide, "缺口写回提示词之后，同样的生成预算盖得更快。", 0.7, 1.45, 12, 0.6, 24, INK)
    cards = [
        ("运费函数", "4 轮 vs 8 轮", "反馈少走了重复组合"),
        ("门禁函数", f"4 条时 {mid_f['statement_percent']}% vs {mid_b['statement_percent']}%", "终点只差 1 轮，中段已分开"),
        ("接口", "mock 与在线模型同一上下文", "本次故意不发请求"),
    ]
    for index, (head, big, note) in enumerate(cards):
        left = 0.55 + index * 4.2
        shape = slide.shapes.add_shape(1, Inches(left), Inches(2.4), Inches(3.95), Inches(3.3))
        shape.fill.solid()
        shape.fill.fore_color.rgb = PptColor.from_string("FFFFFF")
        shape.line.color.rgb = PptColor.from_string("E2DDD4")
        _text(slide, head, left + 0.2, 2.6, 3.5, 0.4, 16, MUTED)
        _text(slide, big, left + 0.2, 3.15, 3.5, 1.2, 26, BLUE, True)
        _text(slide, note, left + 0.2, 4.55, 3.5, 0.8, 16, INK)
    _footer(slide, 12)

    out = root / "docs" / "答辩PPT.pptx"
    prs.save(out)
    return out


def main() -> None:
    root = project_root()
    summary = json.loads((root / "artifacts" / "summary.json").read_text(encoding="utf-8"))
    import importlib.util

    spec = importlib.util.spec_from_file_location("render_preview", root / "experiments" / "render_preview.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    figures = root / "artifacts" / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    preview.draw_charts(summary, figures)
    docx = build_docx(root, summary)
    pptx = build_pptx(root, summary)
    print(docx)
    print(pptx)


if __name__ == "__main__":
    main()
