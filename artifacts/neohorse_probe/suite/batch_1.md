

import pytest
from datetime import date

from subjects.ledger import (
    open_books,
    Account,
    Currency,
    JournalEntry,
    DuplicateAccountException,
    JournalEntryInvalidException,
    PeriodClosedForNormalEntryException,
    InvalidDateException,
    UnknownCurrencyException,
    SettlementOverdueException,
    EmptyJournalEntryException,
)


def _fresh_ledger():
    """创建全新 ledger 实例，内部已注册默认币种、科目、期间及汇率。"""
    return open_books()


def test_b01_duplicate_account_registration():
    """测试：重复注册账户抛 DuplicateAccountException"""
    ledger1 = _fresh_ledger()
    ledger2 = _fresh_ledger()

    acc = ledger1.add_account("资产类 - 现金", Currency.CNY)
    assert isinstance(acc, Account)
    assert acc.name == "资产类 - 现金"
    assert acc.currency == Currency.CNY

    with pytest.raises(DuplicateAccountException) as exc_info:
        ledger2.add_account("资产类 - 现金", Currency.CNY)
    assert type(exc_info.value).__name__ == "DuplicateAccountException"
    assert "资产类 - 现金" in str(exc_info.value) or "Duplicate" in str(exc_info.value)

    retrieved = ledger1.get_account("资产类 - 现金")
    assert retrieved is not None
    assert retrieved.currency == Currency.CNY
    assert len(ledger1.accounts) == 6


def test_b02_duplicate_period_registration():
    """测试：重复注册期间抛 DuplicateAccountException"""
    ledger1 = _fresh_ledger()
    ledger2 = _fresh_ledger()

    period1 = ledger1.create_period(year=2025, period_number=3, name="三月")
    assert period1.year == 2025
    assert period1.period_number == 3
    assert period1.period_key == "2025-03"
    assert not period1.is_closed

    with pytest.raises(DuplicateAccountException) as exc_info:
        ledger2.create_period(year=2025, period_number=3, name="三月")
    assert type(exc_info.value).__name__ == "DuplicateAccountException"
    assert "2025-03" in str(exc_info.value) or "Duplicate" in str(exc_info.value)

    retrieved = ledger1.get_period(period_key="2025-03")
    assert retrieved is not None
    assert retrieved.period_key == "2025-03"
    assert retrieved.name == "三月"

    period_keys = {p.period_key for p in ledger2.periods} if hasattr(ledger2, "periods") else set()
    assert period_keys == {"2025-01", "2025-02"}


def test_b03_period_does_not_exist():
    """测试：期间不存在，create_journal_entry 抛 PeriodClosedForNormalEntryException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2024, period_number=1, title="无效期间分录")
    assert isinstance(entry, JournalEntry)
    assert entry.period_key == "2024-01"

    with pytest.raises(PeriodClosedForNormalEntryException) as exc_info:
        entry.post()
    assert type(exc_info.value).__name__ == "PeriodClosedForNormalEntryException"
    assert "2024-01" in str(exc_info.value) or "不存在" in str(exc_info.value)

    assert entry.posted is False
    assert len(entry.lines) == 0

    for year, num in [(2025, 1), (2025, 2)]:
        pk = f"{year}-{num:02d}"
        found = ledger.get_period(pk)
        assert found is not None
        assert found.period_key == pk


def test_b04_date_before_period():
    """测试：日期早于期间开始，抛 InvalidDateException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="日期过早")
    entry.transaction_date = date(2024, 12, 31)

    assert isinstance(entry.transaction_date, date)
    assert entry.transaction_date < date(2025, 1, 1)

    with pytest.raises(InvalidDateException) as exc_info:
        entry.post()
    assert type(exc_info.value).__name__ == "InvalidDateException"
    assert "2024-12-31" in str(exc_info.value) or "日期" in str(exc_info.value)

    assert entry.posted is False
    assert len(entry.lines) == 0

    entry2 = ledger.create_journal_entry(year=2025, period_number=1, title="日期正常")
    entry2.transaction_date = date(2025, 1, 15)
    assert entry2.transaction_date >= date(2025, 1, 1)
    assert entry2.transaction_date <= date(2025, 1, 31)
    assert entry2.posted is False


def test_b05_date_after_period():
    """测试：日期晚于期间结束，抛 InvalidDateException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="日期过晚")
    entry.transaction_date = date(2025, 2, 1)

    assert entry.transaction_date > date(2025, 1, 31)

    with pytest.raises(InvalidDateException) as exc_info:
        entry.post()
    assert type(exc_info.value).__name__ == "InvalidDateException"
    assert "2025-02-01" in str(exc_info.value) or "日期" in str(exc_info.value)

    assert entry.posted is False
    assert len(entry.lines) == 0

    entry2 = ledger.create_journal_entry(year=2025, period_number=2, title="二月正常")
    entry2.transaction_date = date(2025, 2, 15)
    assert entry2.transaction_date >= date(2025, 2, 1)
    assert entry2.transaction_date <= date(2025, 2, 28)


def test_b06_same_currency_two_rows_balanced():
    """测试：同币种两行平衡过账，核对 total_debit 与 total_credit"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="同币种平衡")
    entry.transaction_date = date(2025, 1, 10)

    line1 = entry.add_line(account="现金", amount_local=1000.0, currency=Currency.CNY)
    line2 = entry.add_line(account="银行存款", amount_local=-1000.0, currency=Currency.CNY)

    assert line1.amount_local == 1000.0
    assert line2.amount_local == -1000.0
    assert line1.currency == Currency.CNY
    assert line2.currency == Currency.CNY
    assert entry.is_balanced() is True

    total_debit = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    total_credit = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert total_debit == 1000.0
    assert total_credit == 1000.0
    assert total_debit == total_credit

    entry.post()
    assert entry.posted is True
    assert total_debit == total_credit
    assert len(entry.lines) == 2

    entry2 = ledger.create_journal_entry(year=2025, period_number=1, title="外币转换测试")
    entry2.transaction_date = date(2025, 1, 15)
    line3 = entry2.add_line(account="外汇应收", amount_local=-100.0, currency=Currency.USD)
    converted = ledger.convert_foreign_to_local(line3.amount_local, line3.currency, date(2025, 1, 15))
    expected = round(100.0 * 7.2345, 2)
    assert converted == expected
    assert converted == 723.45

    line4 = entry2.add_line(account="银行存款", amount_local=723.45, currency=Currency.CNY)
    assert entry2.is_balanced() is True
    debit_sum = sum(l.amount_local for l in entry2.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry2.lines if l.amount_local < 0))
    assert debit_sum == credit_sum
    entry2.post()
    assert entry2.posted is True


def test_b07_three_rows_balanced_two_debits_one_credit():
    """测试：三行平衡（两借一贷），借贷合计相等"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="两借一贷平衡")
    entry.transaction_date = date(2025, 1, 15)

    line1 = entry.add_line(account="资产 A", amount_local=300.0, currency=Currency.CNY)
    line2 = entry.add_line(account="资产 B", amount_local=200.0, currency=Currency.CNY)
    line3 = entry.add_line(account="负债 C", amount_local=-500.0, currency=Currency.CNY)

    assert line1.amount_local == 300.0
    assert line2.amount_local == 200.0
    assert line3.amount_local == -500.0

    debit_sum = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum == 500.0
    assert credit_sum == 500.0
    assert debit_sum == credit_sum
    assert entry.is_balanced() is True

    entry.post()
    assert entry.posted is True
    assert len(entry.lines) == 3

    account_names = {l.account for l in entry.lines}
    assert "资产 A" in account_names
    assert "资产 B" in account_names
    assert "负债 C" in account_names
    assert entry.total_debit == 500.0
    assert entry.total_credit == 500.0


def test_b08_unbalanced_entries():
    """测试：借贷不平无法过账"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="借贷不平")
    entry.transaction_date = date(2025, 1, 10)

    line1 = entry.add_line(account="现金", amount_local=500.0, currency=Currency.CNY)
    line2 = entry.add_line(account="银行存款", amount_local=-300.0, currency=Currency.CNY)

    assert line1.amount_local == 500.0
    assert line2.amount_local == -300.0
    assert entry.is_balanced() is False

    debit_sum = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum != credit_sum

    with pytest.raises(Exception) as exc_info:
        entry.post()
    assert exc_info.type.__name__ not in ("NoneType",)

    assert entry.posted is False
    assert len(entry.lines) == 2

    line3 = entry.add_line(account="应付账款", amount_local=-200.0, currency=Currency.CNY)
    assert entry.is_balanced() is True
    debit_sum = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum == credit_sum
    entry.post()
    assert entry.posted is True


def test_b09_empty_entry_posting():
    """测试：空分录过账，balance 通过但 validate_basic_structure 失败抛 DuplicateAccountException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="空分录测试")
    entry.transaction_date = date(2025, 1, 10)

    assert len(entry.lines) == 0
    debit_sum = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum == 0
    assert credit_sum == 0
    assert entry.is_balanced() is True

    with pytest.raises(DuplicateAccountException) as exc_info:
        entry.post()
    assert type(exc_info.value).__name__ == "DuplicateAccountException"
    assert type(exc_info.value).__name__ != "EmptyJournalEntryException"
    assert "EmptyJournalEntry" not in str(exc_info.value)

    assert entry.posted is False
    assert len(entry.lines) == 0


def test_b10_same_account_same_side_duplicate():
    """测试：同一科目在同一侧出现两次，post 抛 DuplicateAccountException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="同一科目同侧重复")
    entry.transaction_date = date(2025, 1, 10)

    line1 = entry.add_line(account="现金", amount_local=500.0, currency=Currency.CNY)
    line2 = entry.add_line(account="现金", amount_local=300.0, currency=Currency.CNY)
    line3 = entry.add_line(account="银行存款", amount_local=-800.0, currency=Currency.CNY)

    assert line1.account == "现金"
    assert line2.account == "现金"
    assert line1.amount_local > 0
    assert line2.amount_local > 0

    with pytest.raises(DuplicateAccountException) as exc_info:
        entry.post()
    assert type(exc_info.value).__name__ == "DuplicateAccountException"
    assert "现金" in str(exc_info.value) or "Duplicate" in str(exc_info.value)

    assert entry.posted is False
    assert len(entry.lines) == 3

    entry2 = ledger.create_journal_entry(year=2025, period_number=1, title="不同科目借方")
    entry2.transaction_date = date(2025, 1, 10)
    line4 = entry2.add_line(account="资产 A", amount_local=300.0, currency=Currency.CNY)
    line5 = entry2.add_line(account="资产 B", amount_local=200.0, currency=Currency.CNY)
    line6 = entry2.add_line(account="负债 C", amount_local=-500.0, currency=Currency.CNY)
    assert entry2.is_balanced() is True
    entry2.post()
    assert entry2.posted is True


def test_b11_duplicate_line_number():
    """测试：重复 line_number，add_line 抛 DuplicateAccountException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="行号重复")
    entry.transaction_date = date(2025, 1, 10)

    line1 = entry.add_line(account="现金", amount_local=500.0, currency=Currency.CNY)
    line_num = line1.line_number
    assert isinstance(line_num, int)
    assert line_num == 1

    with pytest.raises(DuplicateAccountException) as exc_info:
        entry.add_line(account="银行存款", amount_local=300.0, currency=Currency.CNY, line_number=line_num)
    assert type(exc_info.value).__name__ == "DuplicateAccountException"
    assert str(line_num) in str(exc_info.value) or "重复" in str(exc_info.value)

    assert len(entry.lines) == 1
    assert entry.lines[0].account == "现金"
    assert entry.lines[0].amount_local == 500.0

    line2 = entry.add_line(account="银行存款", amount_local=300.0, currency=Currency.CNY, line_number=2)
    assert line2.line_number == 2
    assert len(entry.lines) == 2

    assert entry.is_balanced() is False
    debit_sum = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum == 500.0
    assert credit_sum == 300.0
    assert debit_sum != credit_sum


def test_b12_cant_add_line_after_posting():
    """测试：过账后不能再 add_line，抛 JournalEntryInvalidException"""
    ledger = _fresh_ledger()

    entry = ledger.create_journal_entry(year=2025, period_number=1, title="过账后加行")
    entry.transaction_date = date(2025, 1, 10)

    line1 = entry.add_line(account="现金", amount_local=500.0, currency=Currency.CNY)
    assert line1.line_number == 1
    assert len(entry.lines) == 1
    assert entry.posted is False

    line2 = entry.add_line(account="银行存款", amount_local=-500.0, currency=Currency.CNY)
    assert entry.is_balanced() is True

    entry.post()
    assert entry.posted is True
    assert len(entry.lines) == 2

    with pytest.raises(JournalEntryInvalidException) as exc_info:
        entry.add_line(account="其他科目", amount_local=100.0, currency=Currency.CNY)
    assert type(exc_info.value).__name__ == "JournalEntryInvalidException"
    assert entry.posted is True

    final_count = len(entry.lines)
    assert final_count == 2
    assert entry.lines[0].account == "现金"
    assert entry.lines[1].account == "银行存款"

    entry3 = ledger.create_journal_entry(year=2025, period_number=1, title="草稿加行")
    entry3.transaction_date = date(2025, 1, 10)
    line3 = entry3.add_line(account="草稿科目", amount_local=200.0, currency=Currency.CNY)
    assert line3.line_number == 1
    assert entry3.posted is False
    assert len(entry3.lines) == 1