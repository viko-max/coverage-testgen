"""Ask NeoHorse for a long scenario suite against src/subjects/ledger.py.

Tests import that module. They do not redefine it. Each batch is streamed
with thinking left on. Failures are sent back once so the assertions follow
the implementation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "neohorse_probe" / "suite"
SUITE = OUT / "test_ledger_scenarios.py"
_DEF = re.compile(r"(?m)^def test_[\w]+\(.*?(?=^def test_|\Z)", re.DOTALL)

HEADER = '''"""Long scenario tests for the multi-currency ledger.

The implementation under test is subjects.ledger. These tests do not
redefine it. Amount sign: positive amount_local is a debit, negative is a credit.
"""

from datetime import date
from decimal import Decimal

import pytest

from subjects.ledger import (
    Account,
    AccountType,
    AccountingPeriod,
    AdjustmentType,
    Currency,
    DuplicateAccountException,
    ExchangeRateMissingException,
    InsufficientFundsException,
    InvalidDateException,
    JournalEntryInvalidException,
    JournalEntryLine,
    MultiCurrencySettlementManager,
    NegativeAmountException,
    PeriodClosedForNormalEntryException,
    SettlementOverdueException,
    SettlementType,
    UnknownCurrencyException,
)


def open_books():
    mgr = MultiCurrencySettlementManager("CNY")
    mgr.register_currency(Currency("CNY", "人民币", "¥"))
    mgr.register_currency(Currency("USD", "美元", "$"))
    mgr.register_currency(Currency("EUR", "欧元", "€"))
    mgr.register_currency(Currency("JPY", "日元", "¥"))
    mgr.register_account(Account("1001", "库存现金", AccountType.ASSET, Currency("CNY", "人民币", "¥")))
    mgr.register_account(Account("1002", "银行存款", AccountType.ASSET, Currency("CNY", "人民币", "¥")))
    mgr.register_account(Account("1122", "应收账款", AccountType.ASSET, Currency("CNY", "人民币", "¥")))
    mgr.register_account(Account("2202", "应付账款", AccountType.LIABILITY, Currency("CNY", "人民币", "¥")))
    mgr.register_account(Account("6001", "主营业务收入", AccountType.REVENUE, Currency("CNY", "人民币", "¥")))
    mgr.register_account(Account("6401", "主营业务成本", AccountType.EXPENSE, Currency("CNY", "人民币", "¥")))
    mgr.register_period(AccountingPeriod("P202501", 1, 2025, date(2025, 1, 1), date(2025, 1, 31)))
    mgr.register_period(AccountingPeriod("P202502", 2, 2025, date(2025, 2, 1), date(2025, 2, 28)))
    mgr.register_rate("USD", "CNY", Decimal("7.2345"), date(2025, 1, 10))
    mgr.register_rate("EUR", "CNY", Decimal("7.8012"), date(2025, 1, 10))
    mgr.register_rate("JPY", "CNY", Decimal("0.0482"), date(2025, 1, 10))
    mgr.register_rate("USD", "CNY", Decimal("7.2500"), date(2025, 1, 20))
    return mgr


def balanced_entry(mgr, number, when, period_key, lines):
    entry = mgr.create_journal_entry(number, when, period_key, number)
    for index, (account, local, foreign, currency) in enumerate(lines, start=1):
        entry.add_line(JournalEntryLine(index, account, Decimal(local), Decimal(foreign), currency, number))
    return entry
'''

CONTRACT = """
被测模块只能 import subjects.ledger，禁止再定义同名类。
金额符号：amount_local > 0 是借方，amount_local < 0 是贷方。借贷平衡指正数合计等于负数绝对值合计。
period_key 是 f"{year}-{period_number:02d}"，一月是 2025-01。
open_books() 已经注册 CNY/USD/EUR/JPY、六个科目、一月和二月、以及 USD 在 1月10日 7.2345、1月20日 7.2500，EUR 7.8012，JPY 0.0482。
本位币兑本位币汇率函数直接返回 1，不需要登记 CNY 汇率。
空分录的借贷合计都是 0，is_balanced() 为 True；post 时会先通过平衡检查，再因 validate_basic_structure() 为 False 抛出 DuplicateAccountException，不会抛 EmptyJournalEntryException。
同一科目出现在同一侧两次，post 抛 DuplicateAccountException。
重复 line_number，add_line 抛 DuplicateAccountException。
非草稿 add_line 抛 JournalEntryInvalidException。
期间不存在，create_journal_entry 抛 PeriodClosedForNormalEntryException。
日期不在期间内，create_journal_entry 抛 InvalidDateException。
重复注册账户或期间，抛 DuplicateAccountException。
未注册币种，post 抛 UnknownCurrencyException。
期间 is_closed=True 后，post_journal_entry 抛 PeriodClosedForNormalEntryException。
未过账分录调用 settle_journal_entry 抛 JournalEntryInvalidException。
SettlementType.PARTIAL 且不给金额，抛 SettlementOverdueException。
convert_foreign_to_local 用 amount * rate 后 round 到 2 位。USD 100 在 2025-01-15 应取 1月10日的 7.2345，折合 723.45。
write_off_journal_entry 只返回反向行，不改变原分录状态。
process_fx_variance 正数追加贷方行（amount_local 为负），负数追加借方行。
每个测试至少 35 行，至少 6 个断言，中间步骤都要检查。不要写一行就结束的测试。
只输出新增的 def test_ 函数，使用上面的 open_books 和 balanced_entry。不要解释。
"""

BATCHES = [
    "写 test_b01 到 test_b12。场景要分开：重复注册账户、重复注册期间、期间不存在、日期早于期间、日期晚于期间、同币种两行平衡过账并核对 total_debit 与 total_credit、三行平衡（两借一贷）、借贷不平、空分录过账、同一科目同侧重复、行号重复、过账后不能再 add_line。",
    "写 test_b13 到 test_b24。场景：USD 100 在 1月15日折合 723.45、USD 100 在 1月20日用 7.2500 折合 725.00、EUR 50 折合 390.06、JPY 10000 折合 482.00、缺失 GBP 汇率、过账未知币种、本位币折算仍为原金额、汇率取早于交易日的最近一条、1月9日没有更早汇率时改用之后的 1月10日、三币种混合但本位币借贷平衡、过账后状态变为已过账、posted_by 被写入。",
    "写 test_b25 到 test_b36。场景：关闭一月后普通过账被拒绝、关闭后二月仍可过账、调整类型 CORRECTION 调用 adjust_journal_entry、不平衡的调整被拒绝、红字冲销后行金额正负对调且原分录仍是已过账、冲销行数等于原行数、冲销说明里带原凭证号、部分结算不给金额被拒绝、未过账不能结算、全额结算剩余外币为 0、部分结算 40/100 剩余 60、结算超额 validate_settlement_limit。",
    "写 test_b37 到 test_b48。场景：尾差 +0.15 进贷方、尾差 -0.20 进借方、汇兑损益科目 6900 被自动注册、连续两笔记账后分别冲销、一月关账不影响已过账分录的查询、get_lines_by_direction 借方贷方分开、remove_line 后重新平衡、remove_line 不存在的行号、batch_validate_entries 收集不平分录、batch_validate_entries 收集未知币种、direction 传入非法字符串、注册第四个期间 2025-03 后用 3月日期建账。",
    "写 test_b49 到 test_b60。每个测试是一笔完整业务，不要再测单个异常。包括：出口销售 2000 USD 入账再按 1月20日汇率全额结算、进口 800 EUR 入账后部分结算 300、同一天两张凭证分别过账再分别冲销、关账前最后一张调整凭证、日元小额 13 元尾差、现金与银行对转后再确认收入、四行分录两借两贷、结算后剩余金额再调用 validate_settlement_limit 的边界相等不抛、汇率缺失时结算路径、连续三张凭证的借方合计。每个测试至少 8 个断言。",
]


def load_env() -> None:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def stream_chat(messages: list[dict]) -> tuple[int, str, str]:
    payload = {
        "model": os.environ.get("LLM_MODEL", "neohorse-1-9b"),
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repetition_penalty": 1.0,
        "max_tokens": 32768,
        "stream": True,
        "messages": messages,
    }
    req = urllib.request.Request(
        os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    content: list[str] = []
    reasoning: list[str] = []
    try:
        response = urllib.request.urlopen(req, timeout=900)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        print(f"http {exc.code} {err[:180]}", flush=True)
        return exc.code, "", ""
    with response:
        while True:
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if delta.get("content"):
                content.append(delta["content"])
    text = "".join(content)
    thought = "".join(reasoning)
    if not text.strip() and "def test_" in thought:
        text = thought
    print(f"reasoning_chars={len(thought)} content_chars={len(text)}", flush=True)
    return 200, text, thought


def functions_from(text: str) -> list[str]:
    fenced = re.findall(r"```python\s*(.*?)```", text, re.S)
    body = max(fenced, key=len) if fenced else text
    found = []
    for block in _DEF.findall(body):
        if block.count("\n") < 24:
            continue
        found.append(block.strip() + "\n")
    return found


def write_suite(chunks: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    body = HEADER + "\n\n" + "\n\n".join(chunk.strip() for chunk in chunks) + "\n"
    SUITE.write_text(body, encoding="utf-8")


def run_pytest() -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(SUITE), "-q", "--tb=line"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    (OUT / "pytest.txt").write_text(output, encoding="utf-8")
    return completed.returncode, output


def main() -> int:
    load_env()
    OUT.mkdir(parents=True, exist_ok=True)
    chunks: list[str] = []
    seen: set[str] = set()
    for index, task in enumerate(BATCHES, start=1):
        print(f"batch {index} start", flush=True)
        status, text, _thought = stream_chat(
            [
                {"role": "system", "content": "你是会计系统的测试作者。先核对源码行为，再写长测试。正文只输出 pytest 函数。"},
                {"role": "user", "content": CONTRACT + "\n" + task},
            ]
        )
        (OUT / f"batch_{index}.md").write_text(text, encoding="utf-8")
        if status != 200:
            print(f"batch {index} failed", flush=True)
            continue
        added = 0
        for block in functions_from(text):
            name = block.split("(", 1)[0].replace("def ", "").strip()
            if name in seen:
                continue
            seen.add(name)
            chunks.append(block)
            added += 1
        print(f"batch {index} kept {added} tests, total {len(chunks)}", flush=True)
        write_suite(chunks)
    if not chunks:
        print("no tests")
        return 1
    code, output = run_pytest()
    failed = [line[7:].strip() for line in output.splitlines() if line.startswith("FAILED ")]
    print(output[-500:], flush=True)
    if failed:
        print(f"repair {len(failed)} failures", flush=True)
        names = "\n".join(failed[:12])
        tail = "\n".join(output.splitlines()[-40:])
        status, text, _thought = stream_chat(
            [
                {"role": "system", "content": "只重写失败的测试函数，让断言符合源码真实行为。不要重写实现。"},
                {"role": "user", "content": CONTRACT + "\n失败列表：\n" + names + "\n\npytest 摘要：\n" + tail},
            ]
        )
        (OUT / "repair.md").write_text(text, encoding="utf-8")
        if status == 200:
            replaced = 0
            for block in functions_from(text):
                name = block.split("(", 1)[0].replace("def ", "").strip()
                chunks = [item for item in chunks if not item.startswith(f"def {name}(")]
                chunks.append(block)
                replaced += 1
            print(f"repaired {replaced}", flush=True)
            write_suite(chunks)
            code, output = run_pytest()
            print(output[-400:], flush=True)
    summary = {
        "tests": len(chunks),
        "lines": SUITE.read_text(encoding="utf-8").count("\n") + 1,
        "exit_code": code,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
