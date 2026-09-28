

from subjects.ledger import (
    create_journal_entry, add_line, remove_line,
    post_journal_entry, settle_journal_entry,
    write_off_journal_entry, process_fx_variance,
    convert_foreign_to_local, is_balanced,
    get_lines_by_direction, batch_validate_entries,
    JournalEntryInvalidException,
    DuplicateAccountException,
    PeriodClosedForNormalEntryException,
    InvalidDateException,
    UnknownCurrencyException,
    SettlementOverdueException,
    SettlementType,
)
import pytest
import datetime


def test_b37_rounding_difference_positive_credits_side():
    """尾差 +0.15 进贷方：正数尾差追加贷方行，amount_local 为负"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_foreign=100, currency="USD", date=datetime.date(2025, 1, 15))
    add_line(entry, account="2201", amount_foreign=-100, currency="USD", date=datetime.date(2025, 1, 15))
    assert is_balanced(entry) is True
    assert len(entry.lines) == 2
    assert entry.lines[0].amount_local > 0
    assert entry.lines[1].amount_local < 0
    process_fx_variance(entry, variance_amount=0.15)
    assert len(entry.lines) == 3
    last_line = entry.lines[-1]
    assert last_line.amount_local < 0
    assert abs(last_line.amount_local) == pytest.approx(0.15, rel=1e-6)
    debit_total = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_total = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_total != credit_total
    assert debit_total == pytest.approx(723.45, abs=0.01)
    assert credit_total == pytest.approx(723.60, abs=0.01)
    expected = convert_foreign_to_local(100, "USD", datetime.date(2025, 1, 15))
    assert expected == 723.45
    assert entry.lines[0].account == "1001"
    assert entry.lines[1].account == "2201"
    assert last_line.account in ["6900", "6901"]


def test_b38_rounding_difference_negative_debits_side():
    """尾差 -0.20 进借方：负数尾差追加借方行，amount_local 为正"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_foreign=100, currency="USD", date=datetime.date(2025, 1, 15))
    add_line(entry, account="2201", amount_foreign=-100, currency="USD", date=datetime.date(2025, 1, 15))
    assert is_balanced(entry) is True
    assert len(entry.lines) == 2
    process_fx_variance(entry, variance_amount=-0.20)
    assert len(entry.lines) == 3
    last_line = entry.lines[-1]
    assert last_line.amount_local > 0
    assert abs(last_line.amount_local) == pytest.approx(0.20, rel=1e-6)
    debit_total = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_total = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_total != credit_total
    assert debit_total == pytest.approx(723.65, abs=0.01)
    assert credit_total == pytest.approx(723.45, abs=0.01)
    assert convert_foreign_to_local(100, "USD", datetime.date(2025, 1, 15)) == 723.45
    assert entry.lines[0].account == "1001"
    assert last_line.account in ["6900", "6901"]
    assert sum(l.amount_local for l in entry.lines) == pytest.approx(0.20, abs=0.01)


def test_b39_fx_variance_account_6900_auto_registered():
    """汇兑损益科目 6900 被自动注册"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_foreign=500, currency="EUR", date=datetime.date(2025, 1, 12))
    add_line(entry, account="2201", amount_foreign=-500, currency="EUR", date=datetime.date(2025, 1, 12))
    assert is_balanced(entry) is True
    process_fx_variance(entry, variance_amount=12.50)
    last_line = entry.lines[-1]
    assert last_line.account == "6900"
    assert last_line.amount_local < 0
    assert abs(last_line.amount_local) == pytest.approx(12.50, rel=1e-6)
    eur_rate = convert_foreign_to_local(1, "EUR", datetime.date(2025, 1, 12))
    assert eur_rate == pytest.approx(7.8012, rel=1e-4)
    expected_cny = 500 * eur_rate
    assert abs(entry.lines[0].amount_local - expected_cny) <= 0.01
    assert is_balanced(entry) is False
    entry2 = create_journal_entry("2025-01", draft=True)
    add_line(entry2, account="1002", amount_foreign=200, currency="JPY", date=datetime.date(2025, 1, 14))
    add_line(entry2, account="2201", amount_foreign=-200, currency="JPY", date=datetime.date(2025, 1, 14))
    process_fx_variance(entry2, variance_amount=-3.15)
    assert entry2.lines[-1].amount_local > 0
    assert entry2.lines[-1].account == "6900"
    jpy_rate = convert_foreign_to_local(1, "JPY", datetime.date(2025, 1, 14))
    assert jpy_rate == pytest.approx(0.0482, rel=1e-4)


def test_b40_write_off_two_consecutive_entries_separately():
    """连续两笔记账后分别冲销"""
    entry1 = create_journal_entry("2025-01", draft=True)
    add_line(entry1, account="1001", amount_local=1000, date=datetime.date(2025, 1, 5))
    add_line(entry1, account="2201", amount_local=-1000, date=datetime.date(2025, 1, 5))
    entry2 = create_journal_entry("2025-01", draft=True)
    add_line(entry2, account="1002", amount_local=500, date=datetime.date(2025, 1, 8))
    add_line(entry2, account="5101", amount_local=-500, date=datetime.date(2025, 1, 8))
    post_journal_entry(entry1)
    post_journal_entry(entry2)
    assert is_balanced(entry1) is True
    assert is_balanced(entry2) is True
    write_off_result = write_off_journal_entry(entry1)
    assert len(write_off_result) == 2
    assert write_off_result[0].amount_local == -1000
    assert write_off_result[1].amount_local == 1000
    assert is_balanced(entry1) is True
    assert is_balanced(entry2) is True
    write_off_result2 = write_off_journal_entry(entry2)
    assert len(write_off_result2) == 2
    assert write_off_result2[0].amount_local == -500
    assert write_off_result2[1].amount_local == 500
    assert is_balanced(entry1) is True
    assert is_balanced(entry2) is True
    assert entry1.lines[0].account == "1001"
    assert entry2.lines[1].account == "5101"


def test_b41_january_closing_does_not_affect_query_of_posted_entries():
    """一月关账不影响已过账分录的查询"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_local=2000, date=datetime.date(2025, 1, 3))
    add_line(entry, account="2201", amount_local=-2000, date=datetime.date(2025, 1, 3))
    post_journal_entry(entry)
    assert entry.status == "posted"
    assert is_balanced(entry) is True
    entry.posted_date = datetime.date(2025, 1, 3)
    assert entry.posted_date == datetime.date(2025, 1, 3)
    entry.account_changes.append(("1001", 2000))
    entry.account_changes.append(("2201", -2000))
    entry.period_key = "2025-01"
    from subjects.ledger import set_is_closed
    set_is_closed("2025-01", True)
    assert entry.period_key == "2025-01"
    retrieved = entry
    assert retrieved.lines[0].amount_local == 2000
    assert retrieved.lines[1].amount_local == -2000
    assert len(retrieved.account_changes) == 2
    assert retrieved.status == "posted"
    try:
        post_journal_entry(entry)
        assert False, "should have raised"
    except PeriodClosedForNormalEntryException:
        pass
    assert retrieved.lines[0].account == "1001"
    assert retrieved.posted_date == datetime.date(2025, 1, 3)


def test_b42_get_lines_by_direction_debit_credit_separated():
    """get_lines_by_direction 借方贷方分开"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_local=1000, date=datetime.date(2025, 1, 5))
    add_line(entry, account="1002", amount_local=500, date=datetime.date(2025, 1, 5))
    add_line(entry, account="2201", amount_local=-1200, date=datetime.date(2025, 1, 5))
    add_line(entry, account="5101", amount_local=-300, date=datetime.date(2025, 1, 5))
    debit_lines = get_lines_by_direction([entry], "debit")
    assert len(debit_lines) == 2
    assert all(l.amount_local > 0 for l in debit_lines)
    assert debit_lines[0].account == "1001"
    assert debit_lines[1].account == "1002"
    credit_lines = get_lines_by_direction([entry], "credit")
    assert len(credit_lines) == 2
    assert all(l.amount_local < 0 for l in credit_lines)
    assert credit_lines[0].account == "2201"
    assert credit_lines[1].account == "5101"
    total_debit = sum(l.amount_local for l in debit_lines)
    total_credit = abs(sum(l.amount_local for l in credit_lines))
    assert total_debit == total_credit
    assert total_debit == 1500
    assert total_credit == 1500
    try:
        get_lines_by_direction([entry], "invalid")
        assert False, "should have raised"
    except Exception:
        pass


def test_b43_remove_line_then_rebalance():
    """remove_line 后重新平衡"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_local=1000, date=datetime.date(2025, 1, 5))
    add_line(entry, account="1002", amount_local=500, date=datetime.date(2025, 1, 5))
    add_line(entry, account="2201", amount_local=-1500, date=datetime.date(2025, 1, 5))
    assert is_balanced(entry) is True
    assert len(entry.lines) == 3
    remove_line(entry, 1)
    assert len(entry.lines) == 2
    assert is_balanced(entry) is False
    debit_sum = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum != credit_sum
    add_line(entry, account="2201", amount_local=-500, date=datetime.date(2025, 1, 5))
    assert is_balanced(entry) is True
    assert len(entry.lines) == 3
    assert entry.lines[0].account == "1002"
    assert entry.lines[1].account == "2201"
    assert entry.lines[2].account == "2201"
    debit_sum_after = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
    credit_sum_after = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
    assert debit_sum_after == credit_sum_after
    assert debit_sum_after == 500


def test_b44_remove_nonexistent_line_number():
    """remove_line 不存在的行号"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_local=1000, date=datetime.date(2025, 1, 5))
    add_line(entry, account="2201", amount_local=-1000, date=datetime.date(2025, 1, 5))
    assert len(entry.lines) == 2
    with pytest.raises(Exception):
        remove_line(entry, 99)
    with pytest.raises(Exception):
        remove_line(entry, 0)
    with pytest.raises(Exception):
        remove_line(entry, -1)
    with pytest.raises(Exception):
        remove_line(entry, 5)
    assert len(entry.lines) == 2
    assert entry.lines[0].account == "1001"
    assert entry.lines[1].account == "2201"
    try:
        remove_line(entry, 1)
        remove_line(entry, 1)
        assert False, "should have raised"
    except Exception:
        pass
    assert len(entry.lines) == 1
    assert is_balanced(entry) is False


def test_b45_batch_validate_entries_collect_unbalanced_entries():
    """batch_validate_entries 收集不平分录"""
    entry1 = create_journal_entry("2025-01", draft=True)
    add_line(entry1, account="1001", amount_local=1000, date=datetime.date(2025, 1, 5))
    add_line(entry1, account="2201", amount_local=-1000, date=datetime.date(2025, 1, 5))
    entry2 = create_journal_entry("2025-01", draft=True)
    add_line(entry2, account="1002", amount_local=500, date=datetime.date(2025, 1, 5))
    add_line(entry2, account="2201", amount_local=-300, date=datetime.date(2025, 1, 5))
    entry3 = create_journal_entry("2025-01", draft=True)
    add_line(entry3, account="1003", amount_local=2000, date=datetime.date(2025, 1, 5))
    add_line(entry3, account="5101", amount_local=-1500, date=datetime.date(2025, 1, 5))
    results = batch_validate_entries([entry1, entry2, entry3])
    assert len(results) == 2
    assert entry2 in results
    assert entry3 in results
    assert entry1 not in results
    assert is_balanced(entry1) is True
    assert is_balanced(entry2) is False
    assert is_balanced(entry3) is False
    debit2 = sum(l.amount_local for l in entry2.lines if l.amount_local > 0)
    credit2 = abs(sum(l.amount_local for l in entry2.lines if l.amount_local < 0))
    assert debit2 != credit2
    debit3 = sum(l.amount_local for l in entry3.lines if l.amount_local > 0)
    credit3 = abs(sum(l.amount_local for l in entry3.lines if l.amount_local < 0))
    assert debit3 != credit3
    assert results[0].period_key == "2025-01"
    assert results[1].period_key == "2025-01"


def test_b46_batch_validate_entries_collect_unknown_currency_entries():
    """batch_validate_entries 收集未知币种"""
    entry1 = create_journal_entry("2025-01", draft=True)
    add_line(entry1, account="1001", amount_foreign=100, currency="USD", date=datetime.date(2025, 1, 5))
    add_line(entry1, account="2201", amount_foreign=-100, currency="USD", date=datetime.date(2025, 1, 5))
    entry2 = create_journal_entry("2025-01", draft=True)
    add_line(entry2, account="1002", amount_foreign=50, currency="GBP", date=datetime.date(2025, 1, 5))
    add_line(entry2, account="2201", amount_foreign=-50, currency="GBP", date=datetime.date(2025, 1, 5))
    entry3 = create_journal_entry("2025-01", draft=True)
    add_line(entry3, account="1003", amount_foreign=200, currency="CNY", date=datetime.date(2025, 1, 5))
    add_line(entry3, account="2201", amount_foreign=-200, currency="CNY", date=datetime.date(2025, 1, 5))
    results = batch_validate_entries([entry1, entry2, entry3])
    assert len(results) == 1
    assert entry2 in results
    assert entry1 not in results
    assert entry3 not in results
    try:
        convert_foreign_to_local(100, "GBP", datetime.date(2025, 1, 5))
        assert False, "should have raised"
    except UnknownCurrencyException:
        pass
    cny_rate = convert_foreign_to_local(1, "CNY", datetime.date(2025, 1, 5))
    assert cny_rate == 1
    usd_rate = convert_foreign_to_local(1, "USD", datetime.date(2025, 1, 5))
    assert usd_rate == pytest.approx(7.2345, rel=1e-4)


def test_b47_direction_illegal_string():
    """direction 传入非法字符串"""
    entry = create_journal_entry("2025-01", draft=True)
    add_line(entry, account="1001", amount_local=1000, date=datetime.date(2025, 1, 5))
    add_line(entry, account="2201", amount_local=-1000, date=datetime.date(2025, 1, 5))
    with pytest.raises(Exception):
        get_lines_by_direction([entry], "")
    with pytest.raises(Exception):
        get_lines_by_direction([entry], "DEBIT")
    with pytest.raises(Exception):
        get_lines_by_direction([entry], "Credit")
    with pytest.raises(Exception):
        get_lines_by_direction([entry], "left")
    with pytest.raises(Exception):
        get_lines_by_direction([entry], 123)
    with pytest.raises(Exception):
        get_lines_by_direction([entry], None)
    assert is_balanced(entry) is True
    debit_lines = get_lines_by_direction([entry], "debit")
    assert len(debit_lines) == 1
    assert debit_lines[0].amount_local == 1000
    assert debit_lines[0].account == "1001"
    credit_lines = get_lines_by_direction([entry], "credit")
    assert len(credit_lines) == 1
    assert credit_lines[0].amount_local == -1000


def test_b48_register_march_period_then_create_entry_with_march_date():
    """注册第四个期间 2025-03 后用 3月日期建账"""
    from subjects.ledger import register_period
    entry = create_journal_entry("2025-03", draft=True)
    add_line(entry, account="1001", amount_local=3000, date=datetime.date(2025, 3, 10))
    add_line(entry, account="2201", amount_local=-3000, date=datetime.date(2025, 3, 10))
    assert is_balanced(entry) is True
    assert entry.period_key == "2025-03"
    register_period("2025-03")
    entry2 = create_journal_entry("2025-03", draft=True)
    add_line(entry2, account="1002", amount_foreign=1000, currency="USD", date=datetime.date(2025, 3, 15))
    add_line(entry2, account="2201", amount_foreign=-1000, currency="USD", date=datetime.date(2025, 3, 15))
    usd_on_march = convert_foreign_to_local(1000, "USD", datetime.date(2025, 3, 15))
    assert usd_on_march == pytest.approx(7250.0, abs=0.01)
    post_journal_entry(entry)
    post_journal_entry(entry2)
    assert entry.status == "posted"
    assert entry2.status == "posted"
    feb_entry = create_journal_entry("2025-02", draft=True)
    add_line(feb_entry, account="1003", amount_local=500, date=datetime.date(2025, 2, 20))
    add_line(feb_entry, account="5101", amount_local=-500, date=datetime.date(2025, 2, 20))
    post_journal_entry(feb_entry)
    assert is_balanced(entry) is True
    assert is_balanced(entry2) is True
    assert is_balanced(feb_entry) is True
    jan_entry = create_journal_entry("2025-01", draft=True)
    add_line(jan_entry, account="1004", amount_local=800, date=datetime.date(2025, 1, 2))
    add_line(jan_entry, account="2201", amount_local=-800, date=datetime.date(2025, 1, 2))
    post_journal_entry(jan_entry)
    assert post_journal_entry(jan_entry).status == "posted"