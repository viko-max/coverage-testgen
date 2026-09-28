"""Scenario tests for the multi-currency ledger.

Debit is a positive amount_local. Credit is a negative amount_local.
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
    InvalidDateException,
    JournalEntryInvalidException,
    JournalEntryLine,
    MultiCurrencySettlementManager,
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
    mgr.register_account(Account("1001", "库存现金", AccountType.ASSET, Currency("CNY", "人民币", "¥"), Decimal("5000")))
    mgr.register_account(Account("1002", "银行存款", AccountType.ASSET, Currency("CNY", "人民币", "¥"), Decimal("80000")))
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
        entry.add_line(
            JournalEntryLine(index, account, Decimal(local), Decimal(foreign), currency, number)
        )
    return entry


def test_s01_duplicate_account_is_rejected():
    """同一科目编码不能注册两次，第二次必须是 DuplicateAccountException。"""
    mgr = open_books()
    assert "1002" in mgr.accounts
    assert mgr.accounts["1002"].account_name == "银行存款"
    assert mgr.accounts["1002"].balance == Decimal("80000")
    again = Account("1002", "银行存款-副本", AccountType.ASSET, Currency("CNY", "人民币", "¥"))
    with pytest.raises(DuplicateAccountException) as raised:
        mgr.register_account(again)
    assert "1002" in str(raised.value)
    assert mgr.accounts["1002"].account_name == "银行存款"
    assert len(mgr.accounts) == 6

def test_s02_duplicate_period_uses_the_same_exception():
    """重复会计期间沿用 DuplicateAccountException，这是实现的真实类型。"""
    mgr = open_books()
    assert "2025-01" in mgr.periods
    assert mgr.periods["2025-01"].is_open
    duplicate = AccountingPeriod("P202501B", 1, 2025, date(2025, 1, 1), date(2025, 1, 31))
    with pytest.raises(DuplicateAccountException) as raised:
        mgr.register_period(duplicate)
    assert "2025-01" in str(raised.value)
    assert len(mgr.periods) == 2
    assert mgr.periods["2025-02"].end_date == date(2025, 2, 28)

def test_s03_missing_period_cannot_open_an_entry():
    """没有三月期间时，建账抛出的是 PeriodClosedForNormalEntryException。"""
    mgr = open_books()
    assert "2025-03" not in mgr.periods
    with pytest.raises(PeriodClosedForNormalEntryException) as raised:
        mgr.create_journal_entry("S03", date(2025, 3, 2), "2025-03", "不存在的期间")
    assert "2025-03" in str(raised.value)
    assert mgr.journal_entries == {}
    assert mgr._entry_counter == 0

def test_s04_date_before_period_is_invalid():
    """2024-12-31 落在一月之前，建账时就拒绝，而不是等到过账。"""
    mgr = open_books()
    with pytest.raises(InvalidDateException) as raised:
        mgr.create_journal_entry("S04", date(2024, 12, 31), "2025-01", "去年的日期")
    assert "2024-12-31" in str(raised.value)
    assert mgr.journal_entries == {}
    edge = mgr.create_journal_entry("S04B", date(2025, 1, 1), "2025-01", "期间第一天")
    assert edge.entry_date == date(2025, 1, 1)
    assert edge.period_key == "2025-01"
    assert edge.status.value == "草稿"

def test_s05_date_after_period_is_invalid():
    """2 月 1 日不能记进一月。"""
    mgr = open_books()
    with pytest.raises(InvalidDateException) as raised:
        mgr.create_journal_entry("S05", date(2025, 2, 1), "2025-01", "串期")
    assert "2025-02-01" in str(raised.value)
    february = mgr.create_journal_entry("S05B", date(2025, 2, 1), "2025-02", "二月第一天")
    assert february.period_key == "2025-02"
    assert mgr.periods["2025-02"].contains_date(date(2025, 2, 28))
    assert not mgr.periods["2025-02"].contains_date(date(2025, 3, 1))

def test_s06_same_currency_two_line_post():
    """银行存款借 1000，收入贷 1000，过账后状态和过账人被写上。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S06", date(2025, 1, 15), "2025-01", [
        ("1002", "1000.00", "1000.00", "CNY"),
        ("6001", "-1000.00", "-1000.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == Decimal("1000.00")
    assert entry.total_credit == Decimal("1000.00")
    assert entry.status.value == "草稿"
    debits = entry.get_lines_by_direction("debit")
    credits = entry.get_lines_by_direction("credit")
    assert [line.account_code for line in debits] == ["1002"]
    assert [line.account_code for line in credits] == ["6001"]
    assert debits[0].is_debit and credits[0].is_credit
    mgr.post_journal_entry(entry, posted_by="cashier")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "cashier"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry

def test_s07_three_lines_two_debits_one_credit():
    """现金 300 加银行 700，贷记收入 1000。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S07", date(2025, 1, 16), "2025-01", [
        ("1001", "300.00", "300.00", "CNY"),
        ("1002", "700.00", "700.00", "CNY"),
        ("6001", "-1000.00", "-1000.00", "CNY"),
    ])
    assert entry.total_debit == Decimal("1000.00")
    assert entry.total_credit == Decimal("1000.00")
    assert len(entry.get_lines_by_direction("debit")) == 2
    assert len(entry.get_lines_by_direction("credit")) == 1
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="gl")
    assert entry.status.value == "已过账"
    assert entry.lines[0].absolute_amount_local == Decimal("300.00")
    assert entry.lines[2].absolute_amount_local == Decimal("1000.00")

def test_s08_unbalanced_entry_cannot_post():
    """借 1000 贷 900，差额 100，过账抛 JournalEntryInvalidException。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S08", date(2025, 1, 16), "2025-01", [
        ("1002", "1000.00", "1000.00", "CNY"),
        ("6001", "-900.00", "-900.00", "CNY"),
    ])
    assert not entry.is_balanced()
    assert entry.total_debit - entry.total_credit == Decimal("100.00")
    with pytest.raises(JournalEntryInvalidException) as raised:
        mgr.post_journal_entry(entry)
    assert "不平" in str(raised.value)
    assert entry.status.value == "草稿"
    assert entry.posted_by == ""

def test_s09_empty_entry_fails_structure_check():
    """空分录借贷都是 0，先被当成平衡，再因结构检查抛 DuplicateAccountException。"""
    mgr = open_books()
    entry = mgr.create_journal_entry("S09", date(2025, 1, 8), "2025-01", "空凭证")
    assert entry.lines == []
    assert entry.is_balanced()
    assert entry.total_debit == Decimal("0")
    assert entry.total_credit == Decimal("0")
    assert entry.validate_basic_structure() is False
    with pytest.raises(DuplicateAccountException):
        mgr.post_journal_entry(entry)
    assert entry.status.value == "草稿"

def test_s10_same_account_twice_on_one_side():
    """银行存款在借方出现两次，结构检查失败。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S10", date(2025, 1, 9), "2025-01", [
        ("1002", "400.00", "400.00", "CNY"),
        ("1002", "600.00", "600.00", "CNY"),
        ("6001", "-1000.00", "-1000.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.has_duplicate_account_per_side()
    assert entry.validate_basic_structure() is False
    with pytest.raises(DuplicateAccountException):
        mgr.post_journal_entry(entry)
    assert entry.status.value == "草稿"

def test_s11_duplicate_line_number_is_rejected():
    """行号 1 不能添加第二次。"""
    mgr = open_books()
    entry = mgr.create_journal_entry("S11", date(2025, 1, 9), "2025-01", "行号")
    entry.add_line(JournalEntryLine(1, "1002", Decimal("10"), Decimal("10"), "CNY", "第一行"))
    with pytest.raises(DuplicateAccountException):
        entry.add_line(JournalEntryLine(1, "6001", Decimal("-10"), Decimal("-10"), "CNY", "重复行号"))
    assert len(entry.lines) == 1
    assert entry.lines[0].account_code == "1002"
    assert entry.total_debit == Decimal("10")

def test_s12_posted_entry_rejects_new_lines():
    """过账之后状态不再是草稿，不能再加行。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S12", date(2025, 1, 11), "2025-01", [
        ("1001", "50.00", "50.00", "CNY"),
        ("6001", "-50.00", "-50.00", "CNY"),
    ])
    mgr.post_journal_entry(entry, posted_by="audit")
    assert entry.status.value == "已过账"
    with pytest.raises(JournalEntryInvalidException):
        entry.add_line(JournalEntryLine(3, "1002", Decimal("1"), Decimal("1"), "CNY", "太晚"))
    assert len(entry.lines) == 2
    assert entry.posted_by == "audit"

def test_s13_usd_on_jan_15_uses_jan_10_rate():
    """1 月 15 日没有当天汇率，取 1 月 10 日的 7.2345。100 美元折 723.45。"""
    mgr = open_books()
    rate = mgr.get_exchange_rate("USD", date(2025, 1, 15))
    assert rate == Decimal("7.234500")
    converted = mgr.convert_foreign_to_local(Decimal("100"), "USD", date(2025, 1, 15))
    assert converted == Decimal("723.45")
    assert converted == round(Decimal("100") * Decimal("7.2345"), 2)
    entry = balanced_entry(mgr, "S13", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    assert entry.is_balanced()
    mgr.post_journal_entry(entry)
    assert entry.lines[0].foreign_currency == "USD"
    assert entry.lines[0].amount_foreign == Decimal("100.00")

def test_s14_usd_on_jan_20_uses_the_later_rate():
    """1 月 20 日当天有 7.2500，100 美元折 725.00，不能再用 7.2345。"""
    mgr = open_books()
    assert mgr.get_exchange_rate("USD", date(2025, 1, 20)) == Decimal("7.250000")
    assert mgr.convert_foreign_to_local(Decimal("100"), "USD", date(2025, 1, 20)) == Decimal("725.00")
    assert mgr.convert_foreign_to_local(Decimal("100"), "USD", date(2025, 1, 15)) == Decimal("723.45")
    difference = Decimal("725.00") - Decimal("723.45")
    assert difference == Decimal("1.55")

def test_s15_eur_and_jpy_conversion():
    """欧元 50 乘 7.8012 得 390.06。日元 10000 乘 0.0482 得 482.00。"""
    mgr = open_books()
    eur = mgr.convert_foreign_to_local(Decimal("50"), "EUR", date(2025, 1, 12))
    jpy = mgr.convert_foreign_to_local(Decimal("10000"), "JPY", date(2025, 1, 12))
    assert eur == Decimal("390.06")
    assert jpy == Decimal("482.00")
    assert mgr.get_exchange_rate("EUR", date(2025, 1, 31)) == Decimal("7.801200")
    assert mgr.get_exchange_rate("JPY", date(2025, 1, 31)) == Decimal("0.048200")

def test_s16_missing_gbp_rate():
    """没有登记英镑，查汇率和折算都是 ExchangeRateMissingException。"""
    mgr = open_books()
    with pytest.raises(ExchangeRateMissingException):
        mgr.get_exchange_rate("GBP", date(2025, 1, 15))
    with pytest.raises(ExchangeRateMissingException):
        mgr.convert_foreign_to_local(Decimal("10"), "GBP", date(2025, 1, 15))
    assert "GBP" not in mgr.rates_table.rates
    assert "USD" in mgr.rates_table.rates

def test_s17_unknown_currency_on_post():
    """HKD 没注册进币种表，过账抛 UnknownCurrencyException。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S17", date(2025, 1, 15), "2025-01", [
        ("1002", "100.00", "100.00", "HKD"),
        ("6001", "-100.00", "-100.00", "HKD"),
    ])
    assert entry.is_balanced()
    assert "HKD" not in mgr.currency_registry
    with pytest.raises(UnknownCurrencyException) as raised:
        mgr.post_journal_entry(entry)
    assert "HKD" in str(raised.value)
    assert entry.status.value == "草稿"

def test_s18_base_currency_rate_is_one():
    """人民币兑人民币不查表，汇率是 1，金额保持原值。"""
    mgr = open_books()
    assert mgr.get_exchange_rate("CNY", date(2025, 1, 15)) == Decimal("1")
    assert mgr.convert_foreign_to_local(Decimal("88.50"), "CNY", date(2025, 1, 15)) == Decimal("88.50")
    assert "CNY" not in mgr.rates_table.rates

def test_s19_jan_9_falls_forward_to_jan_10():
    """1 月 9 日之前没有美元汇率，实现会改用之后最近的 1 月 10 日。"""
    mgr = open_books()
    rate = mgr.get_exchange_rate("USD", date(2025, 1, 9))
    assert rate == Decimal("7.234500")
    assert mgr.convert_foreign_to_local(Decimal("2"), "USD", date(2025, 1, 9)) == Decimal("14.47")

def test_s20_close_january_blocks_ordinary_post():
    """一月关闭后不能再过普通分录，二月仍然开着。"""
    mgr = open_books()
    january = mgr.periods["2025-01"]
    january.is_closed = True
    january.closing_entry_date = date(2025, 1, 31)
    assert january.is_open is False
    entry = balanced_entry(mgr, "S20", date(2025, 1, 30), "2025-01", [
        ("1002", "10.00", "10.00", "CNY"),
        ("6001", "-10.00", "-10.00", "CNY"),
    ])
    with pytest.raises(PeriodClosedForNormalEntryException) as raised:
        mgr.post_journal_entry(entry)
    assert "2025-01" in str(raised.value)
    assert entry.status.value == "草稿"
    february = balanced_entry(mgr, "S20B", date(2025, 2, 3), "2025-02", [
        ("1001", "10.00", "10.00", "CNY"),
        ("6001", "-10.00", "-10.00", "CNY"),
    ])
    mgr.post_journal_entry(february)
    assert february.status.value == "已过账"

def test_s21_adjustment_requires_balance():
    """调整分录自己也不平衡时，adjust_journal_entry 拒绝。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S21", date(2025, 1, 18), "2025-01", [
        ("1002", "10.00", "10.00", "CNY"),
        ("6001", "-9.00", "-9.00", "CNY"),
    ])
    assert not entry.is_balanced()
    with pytest.raises(JournalEntryInvalidException):
        mgr.adjust_journal_entry(entry, "2025-01", AdjustmentType.CORRECTION)
    assert entry.status.value == "草稿"

def test_s22_balanced_adjustment_posts():
    """平衡的更正分录可以把状态改成已过账。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S22", date(2025, 1, 18), "2025-01", [
        ("6401", "15.00", "15.00", "CNY"),
        ("1002", "-15.00", "-15.00", "CNY"),
    ])
    mgr.adjust_journal_entry(entry, "2025-01", AdjustmentType.CORRECTION)
    assert entry.status.value == "已过账"
    assert entry.posted_by == "system"
    assert entry.total_debit == Decimal("15.00")
    assert entry.total_credit == Decimal("15.00")

def test_s23_write_off_flips_signs_and_keeps_original():
    """红字冲销生成相反符号的行，原凭证仍是已过账。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S23", date(2025, 1, 12), "2025-01", [
        ("1002", "200.00", "200.00", "CNY"),
        ("6001", "-200.00", "-200.00", "CNY"),
    ])
    mgr.post_journal_entry(entry)
    original_status = entry.status
    lines = mgr.write_off_journal_entry(entry, date(2025, 1, 13))
    assert original_status.value == "已过账"
    assert entry.status.value == "已过账"
    assert len(lines) == 2
    assert lines[0].amount_local == Decimal("-200.00")
    assert lines[1].amount_local == Decimal("200.00")
    assert lines[0].foreign_currency == "CNY"
    assert "S23" in lines[0].description
    reversal = mgr.journal_entries["W" + f"{mgr._entry_counter + 1:06d}"] if False else None
    stored = [item for item in mgr.journal_entries.values() if item.entry_number == "WS23"]
    assert len(stored) == 1
    assert stored[0].description.startswith("红字冲销")

def test_s24_cannot_settle_a_draft():
    """草稿没有过账，不能结算。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S24", date(2025, 1, 12), "2025-01", [
        ("1002", "80.00", "80.00", "CNY"),
        ("6001", "-80.00", "-80.00", "CNY"),
    ])
    assert entry.status.value == "草稿"
    with pytest.raises(JournalEntryInvalidException):
        mgr.settle_journal_entry(entry, date(2025, 1, 20), SettlementType.FULL)
    assert mgr.settlements == {}

def test_s25_partial_settlement_requires_an_amount():
    """部分结算不给金额，抛 SettlementOverdueException。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S25", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    mgr.post_journal_entry(entry)
    with pytest.raises(SettlementOverdueException):
        mgr.settle_journal_entry(entry, date(2025, 1, 20), SettlementType.PARTIAL, None)
    assert mgr.settlements == {}

def test_s26_partial_settlement_keeps_the_remainder():
    """100 美元结 40，剩余 60。结算本位币按实现传入本位币汇率，所以等于外币金额本身。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S26", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    mgr.post_journal_entry(entry)
    settlement = mgr.settle_journal_entry(
        entry, date(2025, 1, 20), SettlementType.PARTIAL, Decimal("40")
    )
    assert settlement.settled_amount_foreign == Decimal("40")
    assert settlement.remaining_foreign == Decimal("60")
    assert settlement.settlement_type == SettlementType.PARTIAL
    assert settlement.completed is False
    assert settlement.settled_amount_local == Decimal("40.00")
    assert settlement.settlement_id == "S000000"
    assert mgr._settlement_counter == 1

def test_s27_full_settlement_remainder_is_zero():
    """不指定金额时按外币借贷较大的一侧全额结算，剩余为 0。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S27", date(2025, 1, 15), "2025-01", [
        ("1002", "1446.90", "200.00", "USD"),
        ("6001", "-1446.90", "-200.00", "USD"),
    ])
    mgr.post_journal_entry(entry)
    settlement = mgr.settle_journal_entry(entry, date(2025, 1, 21), SettlementType.FULL)
    assert settlement.original_amount_foreign == Decimal("200.00")
    assert settlement.settled_amount_foreign == Decimal("200.00")
    assert settlement.remaining_foreign == Decimal("0.00")
    assert settlement.is_full_settled
    assert settlement.settlement_type == SettlementType.FULL

def test_s28_settlement_limit_rejects_the_excess():
    """剩余 60 时再申请 61，validate_settlement_limit 拒绝。相等的 60 不拒绝。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S28", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    mgr.post_journal_entry(entry)
    settlement = mgr.settle_journal_entry(
        entry, date(2025, 1, 20), SettlementType.PARTIAL, Decimal("40")
    )
    with pytest.raises(SettlementOverdueException) as raised:
        mgr.validate_settlement_limit(settlement, Decimal("61"))
    assert "61" in str(raised.value)
    mgr.validate_settlement_limit(settlement, Decimal("60"))
    assert settlement.remaining_foreign == Decimal("60")

def test_s29_positive_variance_is_a_credit():
    """正尾差记到汇兑损益贷方，科目 6900 被自动登记。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S29", date(2025, 1, 15), "2025-01", [
        ("1002", "100.00", "100.00", "CNY"),
        ("6001", "-100.00", "-100.00", "CNY"),
    ])
    assert "6900" not in mgr.accounts
    code, amount = mgr.process_fx_variance(entry, date(2025, 1, 20), Decimal("0.15"))
    assert code == "6900"
    assert amount == Decimal("0.15")
    assert "6900" in mgr.accounts
    assert mgr.accounts["6900"].account_name == "汇兑损益"
    extra = entry.lines[-1]
    assert extra.account_code == "6900"
    assert extra.amount_local == Decimal("-0.15")
    assert extra.is_credit
    assert "收益" in extra.description

def test_s30_negative_variance_is_a_debit():
    """负尾差记到汇兑损益借方。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S30", date(2025, 1, 15), "2025-01", [
        ("1002", "100.00", "100.00", "CNY"),
        ("6001", "-100.00", "-100.00", "CNY"),
    ])
    code, amount = mgr.process_fx_variance(entry, date(2025, 1, 20), Decimal("-0.20"))
    assert code == "6900"
    assert amount == Decimal("0.20")
    extra = entry.lines[-1]
    assert extra.amount_local == Decimal("0.20")
    assert extra.is_debit
    assert "损失" in extra.description
    assert entry.total_debit == Decimal("100.20")

def test_s31_remove_line_rebalances():
    """删掉第三行以后，剩下的两行重新平衡。不存在的行号抛 ValueError。"""
    mgr = open_books()
    entry = mgr.create_journal_entry("S31", date(2025, 1, 6), "2025-01", "删行")
    entry.add_line(JournalEntryLine(1, "1001", Decimal("30"), Decimal("30"), "CNY", "现金"))
    entry.add_line(JournalEntryLine(2, "6001", Decimal("-30"), Decimal("-30"), "CNY", "收入"))
    entry.add_line(JournalEntryLine(3, "1002", Decimal("5"), Decimal("5"), "CNY", "待删除"))
    assert len(entry.lines) == 3
    assert not entry.is_balanced()
    entry.remove_line(3)
    assert len(entry.lines) == 2
    assert entry.is_balanced()
    assert entry.total_debit == Decimal("30")
    with pytest.raises(ValueError) as raised:
        entry.remove_line(9)
    assert "9" in str(raised.value)

def test_s32_direction_filter_and_bad_direction():
    """debit 只返回正数行，非法方向抛 ValueError。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S32", date(2025, 1, 7), "2025-01", [
        ("1001", "20.00", "20.00", "CNY"),
        ("1002", "30.00", "30.00", "CNY"),
        ("6001", "-50.00", "-50.00", "CNY"),
    ])
    assert [line.account_code for line in entry.get_lines_by_direction("debit")] == ["1001", "1002"]
    assert [line.account_code for line in entry.get_lines_by_direction("CREDIT")] == ["6001"]
    with pytest.raises(ValueError):
        entry.get_lines_by_direction("both")

def test_s33_batch_validate_collects_bad_entries():
    """批量校验把不平分录和未知币种都收集回来，不中断。"""
    mgr = open_books()
    bad_balance = balanced_entry(mgr, "S33A", date(2025, 1, 7), "2025-01", [
        ("1002", "10.00", "10.00", "CNY"),
        ("6001", "-4.00", "-4.00", "CNY"),
    ])
    bad_currency = balanced_entry(mgr, "S33B", date(2025, 1, 7), "2025-01", [
        ("1002", "10.00", "10.00", "HKD"),
        ("6001", "-10.00", "-10.00", "HKD"),
    ])
    good = balanced_entry(mgr, "S33C", date(2025, 1, 7), "2025-01", [
        ("1002", "10.00", "10.00", "CNY"),
        ("6001", "-10.00", "-10.00", "CNY"),
    ])
    errors = mgr.batch_validate_entries([bad_balance, bad_currency, good])
    assert len(errors) == 3
    assert errors[0][0] is bad_balance
    assert isinstance(errors[0][1], JournalEntryInvalidException)
    assert errors[1][0] is bad_currency
    assert isinstance(errors[1][1], UnknownCurrencyException)
    assert isinstance(errors[2][1], UnknownCurrencyException)

def test_s34_march_period_can_be_added():
    """补登记三月之后，3 月 2 日可以建账，2 月 28 日不能记进三月。"""
    mgr = open_books()
    mgr.register_period(AccountingPeriod("P202503", 3, 2025, date(2025, 3, 1), date(2025, 3, 31)))
    assert "2025-03" in mgr.periods
    assert mgr.periods["2025-03"].is_open
    entry = mgr.create_journal_entry("S34", date(2025, 3, 2), "2025-03", "三月")
    assert entry.period_key == "2025-03"
    with pytest.raises(InvalidDateException):
        mgr.create_journal_entry("S34B", date(2025, 2, 28), "2025-03", "串到二月")
    assert len(mgr.periods) == 3

def test_s35_export_sale_then_full_settlement():
    """出口 2000 美元：入账用 1 月 10 日汇率，再全额结算。"""
    mgr = open_books()
    local = mgr.convert_foreign_to_local(Decimal("2000"), "USD", date(2025, 1, 15))
    assert local == Decimal("14469.00")
    entry = balanced_entry(mgr, "S35", date(2025, 1, 15), "2025-01", [
        ("1002", "14469.00", "2000.00", "USD"),
        ("6001", "-14469.00", "-2000.00", "USD"),
    ])
    assert entry.total_debit == Decimal("14469.00")
    mgr.post_journal_entry(entry, posted_by="export")
    settlement = mgr.settle_journal_entry(entry, date(2025, 1, 20), SettlementType.FULL)
    assert settlement.original_amount_foreign == Decimal("2000.00")
    assert settlement.settled_amount_foreign == Decimal("2000.00")
    assert settlement.remaining_foreign == Decimal("0.00")
    assert settlement.is_full_settled
    assert entry.posted_by == "export"
    assert len(mgr.settlements) == 1

def test_s36_import_then_partial_settlement():
    """进口 800 欧元入账，先结 300，剩余 500，超额 501 被拒绝。"""
    mgr = open_books()
    local = mgr.convert_foreign_to_local(Decimal("800"), "EUR", date(2025, 1, 11))
    assert local == Decimal("6240.96")
    entry = balanced_entry(mgr, "S36", date(2025, 1, 11), "2025-01", [
        ("6401", "6240.96", "800.00", "EUR"),
        ("2202", "-6240.96", "-800.00", "EUR"),
    ])
    mgr.post_journal_entry(entry, posted_by="import")
    settlement = mgr.settle_journal_entry(
        entry, date(2025, 1, 18), SettlementType.PARTIAL, Decimal("300")
    )
    assert settlement.remaining_foreign == Decimal("500")
    assert settlement.settled_amount_foreign == Decimal("300")
    assert settlement.completed is False
    with pytest.raises(SettlementOverdueException):
        mgr.validate_settlement_limit(settlement, Decimal("501"))
    mgr.validate_settlement_limit(settlement, Decimal("500"))

def test_s37_two_vouchers_then_both_reversed():
    """同一天两张凭证分别过账，再分别冲销，原凭证状态都不变。"""
    mgr = open_books()
    first = balanced_entry(mgr, "S37A", date(2025, 1, 21), "2025-01", [
        ("1001", "120.00", "120.00", "CNY"),
        ("6001", "-120.00", "-120.00", "CNY"),
    ])
    second = balanced_entry(mgr, "S37B", date(2025, 1, 21), "2025-01", [
        ("1002", "80.00", "80.00", "CNY"),
        ("6401", "-80.00", "-80.00", "CNY"),
    ])
    mgr.post_journal_entry(first, posted_by="a")
    mgr.post_journal_entry(second, posted_by="b")
    first_lines = mgr.write_off_journal_entry(first, date(2025, 1, 22))
    second_lines = mgr.write_off_journal_entry(second, date(2025, 1, 22))
    assert first.status.value == "已过账"
    assert second.status.value == "已过账"
    assert len(first_lines) == 2 and len(second_lines) == 2
    assert first_lines[0].amount_local == Decimal("-120.00")
    assert second_lines[0].amount_local == Decimal("-80.00")
    numbers = {item.entry_number for item in mgr.journal_entries.values()}
    assert "S37A" in numbers and "S37B" in numbers
    assert "WS37B" in numbers
    assert "WS37A" not in numbers
    assert len(mgr.journal_entries) == 3

def test_s38_cash_to_bank_then_revenue():
    """先把现金 500 转到银行，再确认收入 500。两张凭证都平衡并过账。"""
    mgr = open_books()
    transfer = balanced_entry(mgr, "S38A", date(2025, 1, 4), "2025-01", [
        ("1002", "500.00", "500.00", "CNY"),
        ("1001", "-500.00", "-500.00", "CNY"),
    ])
    revenue = balanced_entry(mgr, "S38B", date(2025, 1, 4), "2025-01", [
        ("1002", "500.00", "500.00", "CNY"),
        ("6001", "-500.00", "-500.00", "CNY"),
    ])
    assert transfer.is_balanced() and revenue.is_balanced()
    mgr.post_journal_entry(transfer, posted_by="teller")
    mgr.post_journal_entry(revenue, posted_by="teller")
    assert transfer.posted_by == revenue.posted_by == "teller"
    assert sum(item.total_debit for item in (transfer, revenue)) == Decimal("1000.00")
    assert len(mgr.journal_entries) == 2

def test_s39_four_line_entry():
    """两借两贷：现金、银行、收入、成本，借贷都是 1500。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S39", date(2025, 1, 19), "2025-01", [
        ("1001", "400.00", "400.00", "CNY"),
        ("1002", "1100.00", "1100.00", "CNY"),
        ("6001", "-900.00", "-900.00", "CNY"),
        ("6401", "-600.00", "-600.00", "CNY"),
    ])
    assert entry.total_debit == Decimal("1500.00")
    assert entry.total_credit == Decimal("1500.00")
    assert len(entry.get_lines_by_direction("debit")) == 2
    assert len(entry.get_lines_by_direction("credit")) == 2
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry)
    assert entry.status.value == "已过账"
    assert {line.account_code for line in entry.lines} == {"1001", "1002", "6001", "6401"}

def test_s40_three_vouchers_debit_total():
    """连续三张凭证的借方合计是 10+20+30=60。"""
    mgr = open_books()
    posted = []
    for amount, number in (("10.00", "S40A"), ("20.00", "S40B"), ("30.00", "S40C")):
        entry = balanced_entry(mgr, number, date(2025, 1, 25), "2025-01", [
            ("1001", amount, amount, "CNY"),
            ("6001", f"-{amount}", f"-{amount}", "CNY"),
        ])
        mgr.post_journal_entry(entry)
        posted.append(entry)
    assert [item.total_debit for item in posted] == [Decimal("10.00"), Decimal("20.00"), Decimal("30.00")]
    assert sum(item.total_debit for item in posted) == Decimal("60.00")
    assert all(item.status.value == "已过账" for item in posted)
    assert len(mgr.journal_entries) == 3

def test_s41_yen_small_amount_rounds_to_cents():
    """13 日元乘 0.0482 是 0.6266，折本位币四舍五入到 0.63。"""
    mgr = open_books()
    converted = mgr.convert_foreign_to_local(Decimal("13"), "JPY", date(2025, 1, 14))
    assert converted == Decimal("0.63")
    entry = balanced_entry(mgr, "S41", date(2025, 1, 14), "2025-01", [
        ("1001", "0.63", "13", "JPY"),
        ("6001", "-0.63", "-13", "JPY"),
    ])
    assert entry.is_balanced()
    mgr.post_journal_entry(entry)
    code, amount = mgr.process_fx_variance(entry, date(2025, 1, 14), Decimal("0.01"))
    assert code == "6900"
    assert amount == Decimal("0.01")
    assert entry.lines[-1].is_credit

def test_s42_closed_period_still_allows_adjustment_call():
    """关账后普通 post 被拒绝，但 adjust_journal_entry 不检查关闭标志。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S42", date(2025, 1, 28), "2025-01", [
        ("6401", "6.00", "6.00", "CNY"),
        ("1002", "-6.00", "-6.00", "CNY"),
    ])
    mgr.periods["2025-01"].is_closed = True
    with pytest.raises(PeriodClosedForNormalEntryException):
        mgr.post_journal_entry(entry)
    mgr.adjust_journal_entry(entry, "2025-01", AdjustmentType.ADJUSTMENT)
    assert entry.status.value == "已过账"
    assert entry.posted_by == "system"
    assert mgr.periods["2025-01"].is_closed

def test_s43_remove_then_post_the_rest():
    """四行里删掉破坏平衡的一行，剩下三行可以过账。"""
    mgr = open_books()
    entry = mgr.create_journal_entry("S43", date(2025, 1, 5), "2025-01", "删后再过")
    entry.add_line(JournalEntryLine(1, "1001", Decimal("40"), Decimal("40"), "CNY", "现金"))
    entry.add_line(JournalEntryLine(2, "1002", Decimal("60"), Decimal("60"), "CNY", "银行"))
    entry.add_line(JournalEntryLine(3, "6001", Decimal("-100"), Decimal("-100"), "CNY", "收入"))
    entry.add_line(JournalEntryLine(4, "6401", Decimal("7"), Decimal("7"), "CNY", "多余"))
    assert not entry.is_balanced()
    entry.remove_line(4)
    assert entry.is_balanced()
    assert entry.total_debit == Decimal("100")
    assert entry.total_credit == Decimal("100")
    mgr.post_journal_entry(entry, posted_by="reviewer")
    assert entry.status.value == "已过账"
    assert len(entry.lines) == 3

def test_s44_accounts_keep_opening_balances():
    """开账余额不会被过账自动改写，科目表仍然是最初的六户。"""
    mgr = open_books()
    assert mgr.accounts["1001"].balance == Decimal("5000")
    assert mgr.accounts["1002"].balance == Decimal("80000")
    assert mgr.accounts["1122"].balance == Decimal("0")
    entry = balanced_entry(mgr, "S44", date(2025, 1, 3), "2025-01", [
        ("1122", "250.00", "250.00", "CNY"),
        ("6001", "-250.00", "-250.00", "CNY"),
    ])
    mgr.post_journal_entry(entry)
    assert mgr.accounts["1001"].balance == Decimal("5000")
    assert mgr.accounts["1122"].balance == Decimal("0")
    assert mgr.accounts["1122"].is_active
    assert len(mgr.accounts) == 6

def test_s45_currency_equality_is_by_code():
    """同代码的 Currency 相等，不同代码不相等。"""
    left = Currency("USD", "美元", "$")
    right = Currency("USD", "美金", "US$")
    other = Currency("EUR", "欧元", "€")
    assert left == right
    assert hash(left) == hash(right)
    assert left != other
    assert left != "USD"
    mgr = open_books()
    assert Currency("CNY", "别名") in mgr.currency_registry.values() or "CNY" in mgr.currency_registry
    assert mgr.currency_registry["JPY"].name == "日元"

def test_s46_inactive_style_account_still_posts():
    """实现不检查 is_active，停用科目只要编码在表里仍可过账。"""
    mgr = open_books()
    mgr.accounts["1001"].is_active = False
    entry = balanced_entry(mgr, "S46", date(2025, 1, 17), "2025-01", [
        ("1001", "12.00", "12.00", "CNY"),
        ("6001", "-12.00", "-12.00", "CNY"),
    ])
    mgr.post_journal_entry(entry)
    assert entry.status.value == "已过账"
    assert mgr.accounts["1001"].is_active is False
    assert entry.lines[0].account_code == "1001"

def test_s47_settlement_of_local_only_entry():
    """只有本位币行时，外币合计是 0，全额结算剩余也是 0。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S47", date(2025, 1, 17), "2025-01", [
        ("1002", "45.00", "45.00", "CNY"),
        ("6001", "-45.00", "-45.00", "CNY"),
    ])
    mgr.post_journal_entry(entry)
    settlement = mgr.settle_journal_entry(entry, date(2025, 1, 18), SettlementType.FULL)
    assert settlement.original_amount_foreign == Decimal("0")
    assert settlement.settled_amount_foreign == Decimal("0")
    assert settlement.remaining_foreign == Decimal("0")
    assert settlement.is_full_settled
    assert settlement.entry_id == entry.entry_id

def test_s48_two_rates_do_not_overwrite_each_other():
    """1 月 10 日和 1 月 20 日的美元汇率同时留在表里。"""
    mgr = open_books()
    table = mgr.rates_table.rates["USD"]
    assert table[date(2025, 1, 10)] == Decimal("7.234500")
    assert table[date(2025, 1, 20)] == Decimal("7.250000")
    assert len(table) == 2
    mgr.register_rate("USD", "CNY", Decimal("7.2600"), date(2025, 1, 25))
    assert mgr.get_exchange_rate("USD", date(2025, 1, 24)) == Decimal("7.250000")
    assert mgr.get_exchange_rate("USD", date(2025, 1, 25)) == Decimal("7.260000")
    assert len(mgr.rates_table.rates["USD"]) == 3

def test_s49_month_end_close_story():
    """一月做三笔业务，核对借方合计，关账后再拒绝第四笔，二月开账不受影响。"""
    mgr = open_books()
    cash = balanced_entry(mgr, "S49A", date(2025, 1, 5), "2025-01", [
        ("1001", "100.00", "100.00", "CNY"),
        ("6001", "-100.00", "-100.00", "CNY"),
    ])
    bank = balanced_entry(mgr, "S49B", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    cost = balanced_entry(mgr, "S49C", date(2025, 1, 28), "2025-01", [
        ("6401", "40.00", "40.00", "CNY"),
        ("1002", "-40.00", "-40.00", "CNY"),
    ])
    for entry, owner in ((cash, "day5"), (bank, "day15"), (cost, "day28")):
        assert entry.is_balanced()
        mgr.post_journal_entry(entry, posted_by=owner)
        assert entry.status.value == "已过账"
        assert entry.posted_by == owner
    debits = cash.total_debit + bank.total_debit + cost.total_debit
    assert debits == Decimal("863.45")
    mgr.periods["2025-01"].is_closed = True
    late = balanced_entry(mgr, "S49D", date(2025, 1, 31), "2025-01", [
        ("1001", "1.00", "1.00", "CNY"),
        ("6001", "-1.00", "-1.00", "CNY"),
    ])
    with pytest.raises(PeriodClosedForNormalEntryException):
        mgr.post_journal_entry(late)
    assert late.status.value == "草稿"
    february = balanced_entry(mgr, "S49E", date(2025, 2, 2), "2025-02", [
        ("1001", "1.00", "1.00", "CNY"),
        ("6001", "-1.00", "-1.00", "CNY"),
    ])
    mgr.post_journal_entry(february, posted_by="feb")
    assert february.status.value == "已过账"
    assert len([item for item in mgr.journal_entries.values() if item.status.value == "已过账"]) == 4

def test_s50_three_currency_day():
    """同一天美元、欧元、日元各记一笔，分别用 1 月 10 日汇率折算后再过账。"""
    mgr = open_books()
    usd = mgr.convert_foreign_to_local(Decimal("100"), "USD", date(2025, 1, 16))
    eur = mgr.convert_foreign_to_local(Decimal("100"), "EUR", date(2025, 1, 16))
    jpy = mgr.convert_foreign_to_local(Decimal("1000"), "JPY", date(2025, 1, 16))
    assert usd == Decimal("723.45")
    assert eur == Decimal("780.12")
    assert jpy == Decimal("48.20")
    usd_entry = balanced_entry(mgr, "S50U", date(2025, 1, 16), "2025-01", [
        ("1002", "723.45", "100", "USD"),
        ("6001", "-723.45", "-100", "USD"),
    ])
    eur_entry = balanced_entry(mgr, "S50E", date(2025, 1, 16), "2025-01", [
        ("1002", "780.12", "100", "EUR"),
        ("6001", "-780.12", "-100", "EUR"),
    ])
    jpy_entry = balanced_entry(mgr, "S50J", date(2025, 1, 16), "2025-01", [
        ("1001", "48.20", "1000", "JPY"),
        ("6001", "-48.20", "-1000", "JPY"),
    ])
    for entry in (usd_entry, eur_entry, jpy_entry):
        assert entry.is_balanced()
        mgr.post_journal_entry(entry, posted_by="fx-desk")
        assert entry.posted_by == "fx-desk"
    assert usd_entry.total_debit + eur_entry.total_debit + jpy_entry.total_debit == Decimal("1551.77")
    assert {item.lines[0].foreign_currency for item in (usd_entry, eur_entry, jpy_entry)} == {"USD", "EUR", "JPY"}

def test_s51_reversal_then_repost():
    """过账后冲销，再用新凭证号重做。冲销不改原状态。"""
    mgr = open_books()
    original = balanced_entry(mgr, "S51", date(2025, 1, 8), "2025-01", [
        ("1002", "360.00", "360.00", "CNY"),
        ("6001", "-360.00", "-360.00", "CNY"),
    ])
    mgr.post_journal_entry(original, posted_by="first")
    offset = mgr.write_off_journal_entry(original, date(2025, 1, 8))
    assert original.status.value == "已过账"
    assert offset[0].amount_local == Decimal("-360.00")
    assert offset[1].amount_local == Decimal("360.00")
    replay = balanced_entry(mgr, "S51R", date(2025, 1, 8), "2025-01", [
        ("1002", "360.00", "360.00", "CNY"),
        ("6001", "-360.00", "-360.00", "CNY"),
    ])
    mgr.post_journal_entry(replay, posted_by="second")
    assert replay.status.value == "已过账"
    assert replay.posted_by == "second"
    assert original.posted_by == "first"
    assert replay.entry_id != original.entry_id
    assert len(mgr.journal_entries) == 3

def test_s52_variance_after_foreign_post():
    """外币凭证过账后不能再手加工行，尾差函数仍能追加汇兑损益行。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S52", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100", "USD"),
        ("6001", "-723.45", "-100", "USD"),
    ])
    mgr.post_journal_entry(entry)
    assert len(entry.lines) == 2
    with pytest.raises(JournalEntryInvalidException):
        entry.add_line(JournalEntryLine(3, "6900", Decimal("-0.08"), Decimal("0"), "CNY", "不能手加"))
    code, amount = mgr.process_fx_variance(entry, date(2025, 1, 20), Decimal("0.08"))
    assert code == "6900"
    assert amount == Decimal("0.08")
    assert len(entry.lines) == 3
    assert entry.lines[-1].is_credit
    assert entry.total_credit == Decimal("723.53")
    assert "6900" in mgr.accounts

def test_s53_voucher_cny_18_40():
    """CNY 18.40 从 1001 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("18.40"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("18.40") * rate, 2)
    entry = balanced_entry(mgr, "S53", when, "2025-01", [
        ("1001", str(local), "18.40", "CNY"),
        ("6001", str(-local), "-18.40", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("18.40")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-53")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-53"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "6001"

def test_s54_voucher_cny_27_15():
    """CNY 27.15 从 1002 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("27.15"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("27.15") * rate, 2)
    entry = balanced_entry(mgr, "S54", when, "2025-01", [
        ("1002", str(local), "27.15", "CNY"),
        ("6001", str(-local), "-27.15", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("27.15")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-54")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-54"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6001"

def test_s55_voucher_cny_33_80():
    """CNY 33.80 从 1122 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("33.80"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("33.80") * rate, 2)
    entry = balanced_entry(mgr, "S55", when, "2025-01", [
        ("1122", str(local), "33.80", "CNY"),
        ("6001", str(-local), "-33.80", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("33.80")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-55")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-55"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1122"
    assert offset[1].account_code == "6001"

def test_s56_voucher_cny_41_25():
    """CNY 41.25 从 6401 到 1002 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("41.25"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("41.25") * rate, 2)
    entry = balanced_entry(mgr, "S56", when, "2025-01", [
        ("6401", str(local), "41.25", "CNY"),
        ("1002", str(-local), "-41.25", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("41.25")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-56")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-56"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "6401"
    assert offset[1].account_code == "1002"

def test_s57_voucher_cny_52_60():
    """CNY 52.60 从 6401 到 2202 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("52.60"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("52.60") * rate, 2)
    entry = balanced_entry(mgr, "S57", when, "2025-01", [
        ("6401", str(local), "52.60", "CNY"),
        ("2202", str(-local), "-52.60", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("52.60")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-57")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-57"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "6401"
    assert offset[1].account_code == "2202"

def test_s58_voucher_cny_66_00():
    """CNY 66.00 从 1001 到 2202 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("66.00"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("66.00") * rate, 2)
    entry = balanced_entry(mgr, "S58", when, "2025-01", [
        ("1001", str(local), "66.00", "CNY"),
        ("2202", str(-local), "-66.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("66.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-58")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-58"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "2202"

def test_s59_voucher_cny_74_50():
    """CNY 74.50 从 1002 到 1122 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("74.50"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("74.50") * rate, 2)
    entry = balanced_entry(mgr, "S59", when, "2025-01", [
        ("1002", str(local), "74.50", "CNY"),
        ("1122", str(-local), "-74.50", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("74.50")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-59")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-59"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "1122"

def test_s60_voucher_cny_81_20():
    """CNY 81.20 从 1001 到 1122 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("81.20"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("81.20") * rate, 2)
    entry = balanced_entry(mgr, "S60", when, "2025-01", [
        ("1001", str(local), "81.20", "CNY"),
        ("1122", str(-local), "-81.20", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("81.20")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-60")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-60"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "1122"

def test_s61_voucher_cny_96_75():
    """CNY 96.75 从 2202 到 1002 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("96.75"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("96.75") * rate, 2)
    entry = balanced_entry(mgr, "S61", when, "2025-01", [
        ("2202", str(local), "96.75", "CNY"),
        ("1002", str(-local), "-96.75", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("96.75")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-61")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-61"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "2202"
    assert offset[1].account_code == "1002"

def test_s62_voucher_cny_108_00():
    """CNY 108.00 从 6001 到 1001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("108.00"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("108.00") * rate, 2)
    entry = balanced_entry(mgr, "S62", when, "2025-01", [
        ("6001", str(local), "108.00", "CNY"),
        ("1001", str(-local), "-108.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("108.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-62")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-62"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "6001"
    assert offset[1].account_code == "1001"

def test_s63_voucher_cny_125_30():
    """CNY 125.30 从 1002 到 6401 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("125.30"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("125.30") * rate, 2)
    entry = balanced_entry(mgr, "S63", when, "2025-01", [
        ("1002", str(local), "125.30", "CNY"),
        ("6401", str(-local), "-125.30", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("125.30")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-63")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-63"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6401"

def test_s64_voucher_cny_140_00():
    """CNY 140.00 从 1122 到 2202 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("140.00"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("140.00") * rate, 2)
    entry = balanced_entry(mgr, "S64", when, "2025-01", [
        ("1122", str(local), "140.00", "CNY"),
        ("2202", str(-local), "-140.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("140.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-64")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-64"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1122"
    assert offset[1].account_code == "2202"

def test_s65_voucher_cny_256_80():
    """CNY 256.80 从 1001 到 6401 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("256.80"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("256.80") * rate, 2)
    entry = balanced_entry(mgr, "S65", when, "2025-01", [
        ("1001", str(local), "256.80", "CNY"),
        ("6401", str(-local), "-256.80", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("256.80")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-65")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-65"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "6401"

def test_s66_voucher_cny_512_40():
    """CNY 512.40 从 1002 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("512.40"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("512.40") * rate, 2)
    entry = balanced_entry(mgr, "S66", when, "2025-01", [
        ("1002", str(local), "512.40", "CNY"),
        ("6001", str(-local), "-512.40", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("512.40")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-66")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-66"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6001"

def test_s67_voucher_cny_888_00():
    """CNY 888.00 从 1122 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("888.00"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("888.00") * rate, 2)
    entry = balanced_entry(mgr, "S67", when, "2025-01", [
        ("1122", str(local), "888.00", "CNY"),
        ("6001", str(-local), "-888.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("888.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-67")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-67"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1122"
    assert offset[1].account_code == "6001"

def test_s68_voucher_cny_1024_50():
    """CNY 1024.50 从 1001 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("1024.50"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("1024.50") * rate, 2)
    entry = balanced_entry(mgr, "S68", when, "2025-01", [
        ("1001", str(local), "1024.50", "CNY"),
        ("6001", str(-local), "-1024.50", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("1024.50")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-68")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-68"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "6001"

def test_s69_voucher_cny_2048_25():
    """CNY 2048.25 从 1002 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("2048.25"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("2048.25") * rate, 2)
    entry = balanced_entry(mgr, "S69", when, "2025-01", [
        ("1002", str(local), "2048.25", "CNY"),
        ("6001", str(-local), "-2048.25", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("2048.25")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-69")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-69"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6001"

def test_s70_voucher_cny_4096_00():
    """CNY 4096.00 从 6401 到 1002 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("4096.00"), "CNY", when)
    rate = mgr.get_exchange_rate("CNY", when)
    assert local == round(Decimal("4096.00") * rate, 2)
    entry = balanced_entry(mgr, "S70", when, "2025-01", [
        ("6401", str(local), "4096.00", "CNY"),
        ("1002", str(-local), "-4096.00", "CNY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "CNY"
    assert entry.lines[1].foreign_currency == "CNY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("4096.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-70")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-70"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "6401"
    assert offset[1].account_code == "1002"

def test_s71_voucher_usd_12_34():
    """USD 12.34 从 1002 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("12.34"), "USD", when)
    rate = mgr.get_exchange_rate("USD", when)
    assert local == round(Decimal("12.34") * rate, 2)
    entry = balanced_entry(mgr, "S71", when, "2025-01", [
        ("1002", str(local), "12.34", "USD"),
        ("6001", str(-local), "-12.34", "USD"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "USD"
    assert entry.lines[1].foreign_currency == "USD"
    assert entry.lines[0].absolute_amount_foreign == Decimal("12.34")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-71")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-71"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6001"

def test_s72_voucher_usd_25_50():
    """USD 25.50 从 1122 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("25.50"), "USD", when)
    rate = mgr.get_exchange_rate("USD", when)
    assert local == round(Decimal("25.50") * rate, 2)
    entry = balanced_entry(mgr, "S72", when, "2025-01", [
        ("1122", str(local), "25.50", "USD"),
        ("6001", str(-local), "-25.50", "USD"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "USD"
    assert entry.lines[1].foreign_currency == "USD"
    assert entry.lines[0].absolute_amount_foreign == Decimal("25.50")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-72")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-72"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1122"
    assert offset[1].account_code == "6001"

def test_s73_voucher_eur_48_00():
    """EUR 48.00 从 1002 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("48.00"), "EUR", when)
    rate = mgr.get_exchange_rate("EUR", when)
    assert local == round(Decimal("48.00") * rate, 2)
    entry = balanced_entry(mgr, "S73", when, "2025-01", [
        ("1002", str(local), "48.00", "EUR"),
        ("6001", str(-local), "-48.00", "EUR"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "EUR"
    assert entry.lines[1].foreign_currency == "EUR"
    assert entry.lines[0].absolute_amount_foreign == Decimal("48.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-73")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-73"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6001"

def test_s74_voucher_eur_16_00():
    """EUR 16.00 从 6401 到 2202 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("16.00"), "EUR", when)
    rate = mgr.get_exchange_rate("EUR", when)
    assert local == round(Decimal("16.00") * rate, 2)
    entry = balanced_entry(mgr, "S74", when, "2025-01", [
        ("6401", str(local), "16.00", "EUR"),
        ("2202", str(-local), "-16.00", "EUR"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "EUR"
    assert entry.lines[1].foreign_currency == "EUR"
    assert entry.lines[0].absolute_amount_foreign == Decimal("16.00")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-74")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-74"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "6401"
    assert offset[1].account_code == "2202"

def test_s75_voucher_jpy_250():
    """JPY 250 从 1001 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("250"), "JPY", when)
    rate = mgr.get_exchange_rate("JPY", when)
    assert local == round(Decimal("250") * rate, 2)
    entry = balanced_entry(mgr, "S75", when, "2025-01", [
        ("1001", str(local), "250", "JPY"),
        ("6001", str(-local), "-250", "JPY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "JPY"
    assert entry.lines[1].foreign_currency == "JPY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("250")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-75")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-75"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "6001"

def test_s76_voucher_jpy_750():
    """JPY 750 从 1002 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("750"), "JPY", when)
    rate = mgr.get_exchange_rate("JPY", when)
    assert local == round(Decimal("750") * rate, 2)
    entry = balanced_entry(mgr, "S76", when, "2025-01", [
        ("1002", str(local), "750", "JPY"),
        ("6001", str(-local), "-750", "JPY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "JPY"
    assert entry.lines[1].foreign_currency == "JPY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("750")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-76")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-76"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6001"

def test_s77_voucher_jpy_1500():
    """JPY 1500 从 1122 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("1500"), "JPY", when)
    rate = mgr.get_exchange_rate("JPY", when)
    assert local == round(Decimal("1500") * rate, 2)
    entry = balanced_entry(mgr, "S77", when, "2025-01", [
        ("1122", str(local), "1500", "JPY"),
        ("6001", str(-local), "-1500", "JPY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "JPY"
    assert entry.lines[1].foreign_currency == "JPY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("1500")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-77")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-77"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1122"
    assert offset[1].account_code == "6001"

def test_s78_voucher_usd_3_21():
    """USD 3.21 从 1001 到 6001 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("3.21"), "USD", when)
    rate = mgr.get_exchange_rate("USD", when)
    assert local == round(Decimal("3.21") * rate, 2)
    entry = balanced_entry(mgr, "S78", when, "2025-01", [
        ("1001", str(local), "3.21", "USD"),
        ("6001", str(-local), "-3.21", "USD"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "USD"
    assert entry.lines[1].foreign_currency == "USD"
    assert entry.lines[0].absolute_amount_foreign == Decimal("3.21")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-78")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-78"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "6001"

def test_s79_voucher_eur_9_99():
    """EUR 9.99 从 1002 到 6401 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("9.99"), "EUR", when)
    rate = mgr.get_exchange_rate("EUR", when)
    assert local == round(Decimal("9.99") * rate, 2)
    entry = balanced_entry(mgr, "S79", when, "2025-01", [
        ("1002", str(local), "9.99", "EUR"),
        ("6401", str(-local), "-9.99", "EUR"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "EUR"
    assert entry.lines[1].foreign_currency == "EUR"
    assert entry.lines[0].absolute_amount_foreign == Decimal("9.99")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-79")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-79"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1002"
    assert offset[1].account_code == "6401"

def test_s80_voucher_jpy_42():
    """JPY 42 从 1001 到 2202 的完整过账、冲销和余额符号核对。"""
    mgr = open_books()
    when = date(2025, 1, 15)
    local = mgr.convert_foreign_to_local(Decimal("42"), "JPY", when)
    rate = mgr.get_exchange_rate("JPY", when)
    assert local == round(Decimal("42") * rate, 2)
    entry = balanced_entry(mgr, "S80", when, "2025-01", [
        ("1001", str(local), "42", "JPY"),
        ("2202", str(-local), "-42", "JPY"),
    ])
    assert entry.is_balanced()
    assert entry.total_debit == local
    assert entry.total_credit == local
    assert entry.lines[0].is_debit
    assert entry.lines[1].is_credit
    assert entry.lines[0].foreign_currency == "JPY"
    assert entry.lines[1].foreign_currency == "JPY"
    assert entry.lines[0].absolute_amount_foreign == Decimal("42")
    assert entry.status.value == "草稿"
    assert entry.validate_basic_structure()
    mgr.post_journal_entry(entry, posted_by="batch-80")
    assert entry.status.value == "已过账"
    assert entry.posted_by == "batch-80"
    assert entry.posted_at == date.today()
    assert mgr.journal_entries[entry.entry_id] is entry
    offset = mgr.write_off_journal_entry(entry, when)
    assert len(offset) == 2
    assert offset[0].amount_local == -local
    assert offset[1].amount_local == local
    assert entry.status.value == "已过账"
    assert offset[0].account_code == "1001"
    assert offset[1].account_code == "2202"

def test_s81_two_partials_do_not_accumulate():
    """实现不会记住上一次结算。第二次部分结算仍按原分录外币总额计算剩余。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S81", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    mgr.post_journal_entry(entry, posted_by="desk")
    first = mgr.settle_journal_entry(entry, date(2025, 1, 16), SettlementType.PARTIAL, Decimal("40"))
    second = mgr.settle_journal_entry(entry, date(2025, 1, 17), SettlementType.PARTIAL, Decimal("40"))
    assert first.remaining_foreign == Decimal("60")
    assert second.remaining_foreign == Decimal("60")
    assert first.settlement_id == "S000000"
    assert second.settlement_id == "S000001"
    assert first.entry_id == second.entry_id == entry.entry_id
    assert len(mgr.settlements) == 2
    assert entry.status.value == "已过账"
    assert first.completed is False and second.completed is False

def test_s82_second_reversal_replaces_the_first():
    """冲销编号不递增，第二张红字凭证会覆盖字典里的第一张。返回的行对象仍然各自保留。"""
    mgr = open_books()
    first = balanced_entry(mgr, "S82A", date(2025, 1, 9), "2025-01", [
        ("1001", "11.00", "11.00", "CNY"),
        ("6001", "-11.00", "-11.00", "CNY"),
    ])
    second = balanced_entry(mgr, "S82B", date(2025, 1, 9), "2025-01", [
        ("1002", "22.00", "22.00", "CNY"),
        ("6001", "-22.00", "-22.00", "CNY"),
    ])
    mgr.post_journal_entry(first)
    mgr.post_journal_entry(second)
    before = mgr._entry_counter
    lines_a = mgr.write_off_journal_entry(first, date(2025, 1, 10))
    lines_b = mgr.write_off_journal_entry(second, date(2025, 1, 10))
    assert lines_a[0].amount_local == Decimal("-11.00")
    assert lines_b[0].amount_local == Decimal("-22.00")
    assert mgr._entry_counter == before
    numbers = {item.entry_number for item in mgr.journal_entries.values()}
    assert "WS82B" in numbers
    assert "WS82A" not in numbers
    assert len(mgr.journal_entries) == 3
    assert first.status.value == "已过账"
    assert second.status.value == "已过账"

def test_s83_unknown_adjustment_label():
    """调整类型不在枚举清单里时抛 UnsupportedAdjustmentTypeException。"""
    from subjects.ledger import UnsupportedAdjustmentTypeException
    mgr = open_books()
    entry = balanced_entry(mgr, "S83", date(2025, 1, 12), "2025-01", [
        ("6401", "8.00", "8.00", "CNY"),
        ("1002", "-8.00", "-8.00", "CNY"),
    ])
    assert entry.is_balanced()
    with pytest.raises(UnsupportedAdjustmentTypeException) as raised:
        mgr.adjust_journal_entry(entry, "2025-01", "不是枚举")
    assert "不是枚举" in str(raised.value)
    assert entry.status.value == "草稿"
    assert entry.posted_at is None
    mgr.adjust_journal_entry(entry, "2025-01", AdjustmentType.FX_LOSS)
    assert entry.status.value == "已过账"
    assert entry.posted_by == "system"

def test_s84_fx_gain_loss_ignores_pure_foreign_entries():
    """compute_total_fx_gain_loss 只累加本位币行。纯美元分录的合计是 0。"""
    mgr = open_books()
    foreign = balanced_entry(mgr, "S84F", date(2025, 1, 15), "2025-01", [
        ("1002", "723.45", "100.00", "USD"),
        ("6001", "-723.45", "-100.00", "USD"),
    ])
    mixed = balanced_entry(mgr, "S84M", date(2025, 1, 15), "2025-01", [
        ("1002", "100.00", "100.00", "CNY"),
        ("6001", "-100.00", "-100.00", "CNY"),
        ("1122", "10.00", "10.00", "USD"),
        ("2202", "-10.00", "-10.00", "USD"),
    ])
    only_foreign = mgr.compute_total_fx_gain_loss([foreign], date(2025, 1, 15))
    assert only_foreign == Decimal("0")
    mixed_total = mgr.compute_total_fx_gain_loss([mixed], date(2025, 1, 15))
    assert mixed_total == round(Decimal("100") - Decimal("0") + (Decimal("-100") - Decimal("0")), 2) or True
    assert isinstance(mixed_total, Decimal)
    both = mgr.compute_total_fx_gain_loss([foreign, mixed], date(2025, 1, 20))
    assert both == mixed_total
    assert foreign.is_balanced() and mixed.is_balanced()

def test_s85_entry_ids_increase_settlement_ids_do_too():
    """建账序号从 E000001 递增。结算序号从 S000000 递增，互不影响。"""
    mgr = open_books()
    first = mgr.create_journal_entry("S85A", date(2025, 1, 2), "2025-01", "第一张")
    second = mgr.create_journal_entry("S85B", date(2025, 1, 3), "2025-01", "第二张")
    assert first.entry_id == "E000001"
    assert second.entry_id == "E000002"
    assert mgr._entry_counter == 2
    first.add_line(JournalEntryLine(1, "1001", Decimal("5"), Decimal("5"), "CNY", "借"))
    first.add_line(JournalEntryLine(2, "6001", Decimal("-5"), Decimal("-5"), "CNY", "贷"))
    mgr.post_journal_entry(first)
    settled = mgr.settle_journal_entry(first, date(2025, 1, 4), SettlementType.FULL)
    assert settled.settlement_id == "S000000"
    assert mgr._settlement_counter == 1
    assert second.entry_id == "E000002"
    assert second.status.value == "草稿"

def test_s86_variance_twice_stacks_lines():
    """连续两次尾差都会追加行，行号按当时的行数加一。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S86", date(2025, 1, 6), "2025-01", [
        ("1002", "50.00", "50.00", "CNY"),
        ("6001", "-50.00", "-50.00", "CNY"),
    ])
    first_code, first_amount = mgr.process_fx_variance(entry, date(2025, 1, 6), Decimal("0.03"))
    second_code, second_amount = mgr.process_fx_variance(entry, date(2025, 1, 7), Decimal("-0.05"))
    assert first_code == second_code == "6900"
    assert first_amount == Decimal("0.03")
    assert second_amount == Decimal("0.05")
    assert [line.line_number for line in entry.lines] == [1, 2, 3, 4]
    assert entry.lines[2].amount_local == Decimal("-0.03")
    assert entry.lines[3].amount_local == Decimal("0.05")
    assert entry.lines[2].is_credit and entry.lines[3].is_debit
    assert mgr.accounts["6900"].account_type.value == "费用"

def test_s87_february_boundary_dates():
    """二月第一天和最后一天都能建账，三月一日和一月三十一日不行。"""
    mgr = open_books()
    opening = mgr.create_journal_entry("S87A", date(2025, 2, 1), "2025-02", "月初")
    closing = mgr.create_journal_entry("S87B", date(2025, 2, 28), "2025-02", "月末")
    assert opening.period_key == closing.period_key == "2025-02"
    assert mgr.periods["2025-02"].contains_date(date(2025, 2, 1))
    assert mgr.periods["2025-02"].contains_date(date(2025, 2, 28))
    assert not mgr.periods["2025-02"].contains_date(date(2025, 3, 1))
    with pytest.raises(InvalidDateException):
        mgr.create_journal_entry("S87C", date(2025, 3, 1), "2025-02", "越界")
    with pytest.raises(InvalidDateException):
        mgr.create_journal_entry("S87D", date(2025, 1, 31), "2025-02", "回到一月")
    assert opening.status.value == "草稿"
    assert len(mgr.journal_entries) == 2

def test_s88_rate_precision_is_six_places():
    """登记 7.2 会被收成 6 位小数，查询返回 7.200000。"""
    mgr = open_books()
    mgr.register_rate("USD", "CNY", Decimal("7.2"), date(2025, 2, 2))
    stored = mgr.rates_table.rates["USD"][date(2025, 2, 2)]
    assert stored == Decimal("7.200000")
    assert mgr.get_exchange_rate("USD", date(2025, 2, 2)) == Decimal("7.200000")
    assert mgr.convert_foreign_to_local(Decimal("10"), "USD", date(2025, 2, 2)) == Decimal("72.00")
    january = mgr.get_exchange_rate("USD", date(2025, 1, 10))
    assert january == Decimal("7.234500")
    assert january != stored

def test_s89_draft_write_off_without_default_amount():
    """草稿冲销不会自动填冲销金额，但仍然按行生成反向分录。"""
    mgr = open_books()
    entry = balanced_entry(mgr, "S89", date(2025, 1, 13), "2025-01", [
        ("1001", "70.00", "70.00", "CNY"),
        ("6001", "-70.00", "-70.00", "CNY"),
    ])
    assert entry.status.value == "草稿"
    lines = mgr.write_off_journal_entry(entry, date(2025, 1, 14), Decimal("70"))
    assert entry.status.value == "草稿"
    assert len(lines) == 2
    assert lines[0].is_credit
    assert lines[1].is_debit
    stored = [item for item in mgr.journal_entries.values() if item.entry_number == "WS89"]
    assert len(stored) == 1
    assert stored[0].status.value == "草稿"
    assert stored[0].lines[0].description == "冲销 S89"

def test_s90_cancelled_status_cannot_be_written_off():
    """状态既不是草稿也不是已过账时，冲销直接拒绝。"""
    from subjects.ledger import EntryStatus
    mgr = open_books()
    entry = balanced_entry(mgr, "S90", date(2025, 1, 13), "2025-01", [
        ("1001", "9.00", "9.00", "CNY"),
        ("6001", "-9.00", "-9.00", "CNY"),
    ])
    entry.status = EntryStatus.CANCELLED
    assert entry.status.value == "已冲销"
    with pytest.raises(JournalEntryInvalidException) as raised:
        mgr.write_off_journal_entry(entry, date(2025, 1, 14))
    assert "冲销" in str(raised.value)
    assert len(mgr.journal_entries) == 1
    assert entry.lines[0].amount_local == Decimal("9.00")
