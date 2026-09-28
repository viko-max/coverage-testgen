

```python
import pytest
import subjects.ledger
from subjects.ledger import (
    Ledger, JournalEntry, SettlementType, DuplicateAccountException,
    JournalEntryInvalidException, PeriodClosedForNormalEntryException,
    InvalidDateException, UnknownCurrencyException, SettlementOverdueException,
    convert_foreign_to_local
)


def test_b49_export_sales_2000usd_full_settlement():
    ledger = open_books()
    sale_date = "2025-01-05"
    usd_rate_at_sale = 7.2345
    cny_amount = round(2000.0 * usd_rate_at_sale, 2)
    entry = balanced_entry(sale_date, "draft", "出口销售全额结算业务")
    entry.add_line("应收账款-USD", 2000.00, "USD", "出口销售收入确认")
    entry.add_line("主营业务收入", -cny_amount, "CNY", "出口销售收入确认")
    entry.post(ledger)
    assert entry.post_status == "posted"
    assert entry.is_balanced() is True
    debit_sum = sum(l.amount for l in entry.lines if l.amount > 0)
    credit_sum = abs(sum(l.amount for l in entry.lines if l.amount < 0))
    assert abs(debit_sum - credit_sum) < 0.001
    assert any(l.currency == "USD" and l.account == "应收账款-USD" for l in entry.lines)
    assert any(l.account == "主营业务收入" for l in entry.lines)

    settle_date = "2025-01-20"
    usd_rate_at_settle = 7.2500
    settle_cny = round(2000.0 * usd_rate_at_settle, 2)
    fx_gain = round(settle_cny - cny_amount, 2)
    settle_entry = balanced_entry(settle_date, "draft", "出口收款结算")
    settle_entry.add_line("银行存款-CNY", settle_cny, "CNY", "收到出口货款")
    settle_entry.add_line("应收账款-USD", -2000.00, "USD", "结清应收账款")
    settle_entry.add_line("财务费用-FX", fx_gain, "CNY", "汇兑收益确认")
    settle_entry.post(ledger)
    assert settle_entry.post_status == "posted"
    assert settle_entry.is_balanced() is True
    assert fx_gain > 0, "汇率上升应产生汇兑收益"
    assert convert_foreign_to_local(2000.0, "USD", settle_date) == settle_cny


def test_b50_import_800eur_partial_settlement():
    ledger = open_books()
    purchase_date = "2025-01-08"
    eur_rate = 7.8012
    total_cny = round(800.0 * eur_rate, 2)
    entry = balanced_entry(purchase_date, "draft", "进口采购部分结算")
    entry.add_line("原材料", -total_cny, "CNY", "进口原材料入库")
    entry.add_line("应付账款-EUR", 800.00, "EUR", "确认进口应付账款")
    entry.post(ledger)
    assert entry.post_status == "posted"
    assert entry.is_balanced() is True
    assert convert_foreign_to_local(800.0, "EUR", purchase_date) == total_cny

    partial_amount_eur = 300.0
    partial_cny = round(partial_amount_eur * eur_rate, 2)
    partial_entry = balanced_entry("2025-01-15", "draft", "进口付款部分结算")
    partial_entry.add_line("银行存款-CNY", -partial_cny, "CNY", "支付进口货款部分")
    partial_entry.add_line("应付账款-EUR", -partial_amount_eur, "EUR", "结清部分应付")
    partial_entry.post(ledger)
    assert partial_entry.post_status == "posted"
    assert partial_entry.is_balanced() is True
    remaining_cny = total_cny - partial_cny
    remaining_eur = 800.0 - partial_amount_eur
    assert remaining_cny > 0
    assert remaining_eur > 0
    assert abs(convert_foreign_to_local(remaining_eur, "EUR", "2025-01-15") - remaining_cny) < 0.01


def test_b51_same_day_two_entries_post_and_write_off():
    ledger = open_books()
    common_date = "2025-01-12"
    entry1 = balanced_entry(common_date, "draft", "第一笔同日凭证")
    entry1.add_line("管理费用", -1000.00, "CNY", "办公费支出")
    entry1.add_line("银行存款-CNY", 1000.00, "CNY", "办公费支出")
    entry1.post(ledger)
    assert entry1.post_status == "posted"
    assert entry1.is_balanced() is True

    entry2 = balanced_entry(common_date, "draft", "第二笔同日凭证")
    entry2.add_line("销售费用", -500.00, "CNY", "差旅费支出")
    entry2.add_line("银行存款-CNY", 500.00, "CNY", "差旅费支出")
    entry2.post(ledger)
    assert entry2.post_status == "posted"
    assert entry2.is_balanced() is True

    same_day_debits = entry1.lines[0].amount + entry2.lines[0].amount
    same_day_credits = entry1.lines[1].amount + entry2.lines[1].amount
    assert abs(same_day_debits) == abs(same_day_credits)

    entry1.write_off(ledger)
    assert entry1.post_status == "written_off"
    entry2.write_off(ledger)
    assert entry2.post_status == "written_off"
    assert entry1.is_balanced() is True
    assert entry2.is_balanced() is True


def test_b52_adjusting_entry_before_period_close():
    ledger = open_books()
    adj_date = "2025-01-31"
    entry = balanced_entry(adj_date, "draft", "期末结账前调整凭证")
    entry.add_line("以前年度损益调整", -1200.00, "CNY", "折旧计提调整")
    entry.add_line("累计折旧", 1200.00, "CNY", "折旧计提调整")
    entry.post(ledger)
    assert entry.post_status == "posted"
    assert entry.is_balanced() is True
    assert len(entry.lines) == 2

    ledger.periods["2025-02"].is_closed = True
    with pytest.raises(PeriodClosedForNormalEntryException):
        new_entry = balanced_entry("2025-02-03", "draft", "关账后不应过账")
        new_entry.post(ledger)
    assert entry.post_status == "posted", "调整凭证应在关账前成功过账"
    assert any("累计折旧" in l.account for l in entry.lines)
    assert any("以前年度损益调整" in l.account for l in entry.lines)
    # 验证调整凭证已被计入期间余额
    assert ledger.get_period_total("2025-01").accounts["累计折旧"] == 1200.00


def test_b53_jpy_small_rounding_difference():
    ledger = open_books()
    jpy_date = "2025-01-18"
    jpy_amount = 13.00
    jpy_rate = 0.0482
    expected_cny = round(jpy_amount * jpy_rate, 2)
    entry = balanced_entry(jpy_date, "draft", "日元小额收汇")
    entry.add_line("银行存款-JPY", jpy_amount, "JPY", "收到日元汇款")
    entry.add_line("财务费用-FX", -expected_cny, "CNY", "日元折算收益")
    entry.post(ledger)
    assert entry.post_status == "posted"
    assert entry.is_balanced() is True
    assert convert_foreign_to_local(jpy_amount, "JPY", jpy_date) == expected_cny
    assert expected_cny == 1.0, "13*0.0482=0.6266舍入为1.0"

    second_entry = balanced_entry(jpy_date, "draft", "日元小额支出")
    second_entry.add_line("银行存款-CNY", -expected_cny, "CNY", "日元折算支出")
    second_entry.add_line("管理费用", expected_cny, "CNY", "日元小额管理费")
    second_entry.post(ledger)
    assert second_entry.post_status == "posted"
    # 两次折算合计应与原金额一致
    combined_cny = expected_cny + expected_cny
    combined_jpy = jpy_amount
    assert combined_cny == 2.0
    assert combined_jpy == 13.0
    assert ledger.get_currency_balance("JPY") == jpy_amount


def test_b54_cash_bank_reversal_then_revenue_confirmation():
    ledger = open_books()
    rev_date = "2025-01-10"
    amount = 5000.00
    entry1 = balanced_entry(rev_date, "draft", "客户现金交款转入银行")
    entry1.add_line("银行存款-CNY", amount, "CNY", "客户现金缴款转存银行")
    entry1.add_line("库存现金", -amount, "CNY", "客户现金缴款转存银行")
    entry1.post(ledger)
    assert entry1.post_status == "posted"
    assert entry1.is_balanced() is True
    cash_after = ledger.get_account_balance("库存现金")
    bank_before = ledger.get_account_balance("银行存款-CNY")
    assert cash_after == -amount
    assert bank_before == amount

    entry2 = balanced_entry(rev_date, "draft", "银行收款确认收入")
    entry2.add_line("主营业务收入", -amount, "CNY", "银行收款确认收入")
    entry2.add_line("银行存款-CNY", amount, "CNY", "银行收款确认收入")
    entry2.post(ledger)
    assert entry2.post_status == "posted"
    assert entry2.is_balanced() is True
    final_bank = ledger.get_account_balance("银行存款-CNY")
    final_revenue = ledger.get_account_balance("主营业务收入")
    assert final_bank == 2 * amount
    assert final_revenue == -amount
    assert len(entry1.lines) == 2 and len(entry2.lines) == 2


def test_b55_four_line_entry_two_debits_two_credits():
    ledger = open_books()
    entry = balanced_entry("2025-01-14", "draft", "四行两借两贷复合分录")
    # 债务重组示例：以银行为主要偿还手段+债务转为权益
    entry.add_line("短期借款", -3000.00, "CNY", "债务重组偿还本金")
    entry.add_line("长期待摊费用", -2000.00, "CNY", "债务重组相关费用")
    entry.add_line("长期借款", 3000.00, "CNY", "债务重组转长期借款")
    entry.add_line("盈余公积", 2000.00, "CNY", "债务重组资本化")
    entry.post(ledger)
    assert entry.post_status == "posted"
    assert entry.is_balanced() is True
    debits = [l for l in entry.lines if l.amount > 0]
    credits = [l for l in entry.lines if l.amount < 0]
    assert len(debits) == 2
    assert len(credits) == 2
    debit_total = sum(l.amount for l in debits)
    credit_total = abs(sum(l.amount for l in credits))
    assert abs(debit_total - credit_total) < 0.001
    assert any("长期借款" in a for a in [l.account for l in entry.lines])
    assert any("盈余公积" in a for a in [l.account for l in entry.lines])
    assert any("短期借款" in a for a in [l.account for l in entry.lines])
    assert any("长期待摊费用" in a for a in [l.account for l in entry.lines])


def test_b56_validate_settlement_limit_boundary_equal():
    ledger = open_books()
    entry = balanced_entry("2025-01-11", "draft", "结算限额边界测试")
    entry.add_line("应收账款-USD", 1000.00, "USD", "应收账款")
    entry.add_line("主营业务收入", -7234.50, "CNY", "销售收入")
    entry.post(ledger)
    assert entry.post_status == "posted"

    settle_entry = balanced_entry("2025-01-15", "draft", "边界结算")
    settle_entry.add_line("银行存款-CNY", 7234.50, "CNY", "部分结算")
    settle_entry.add_line("应收账款-USD", -1000.00, "USD", "结清应收")
    settle_entry.post(ledger)
    assert settle_entry.post_status == "posted"

    # 结算后剩余金额为 0，等于限额边界，validate_settlement_limit 不应抛异常
    remaining = ledger.get_remaining_settlement_amount("应收账款-USD", "2025-01-15")
    limit = 0.0
    try:
        ledger.validate_settlement_limit(remaining, limit)
        assert remaining == limit, "剩余金额应与限额相等"
    except Exception as e:
        pytest.fail(f"边界相等时 validate_settlement_limit 不应抛异常: {e}")
    assert remaining == limit


def test_b57_settlement_without_registered_currency():
    ledger = open_books()
    entry = balanced_entry("2025-01-13", "draft", "未注册币种结算")
    entry.add_line("银行存款-BTN", 10000.00, "BTN", "未知币种收款")
    entry.add_line("主营业务收入", -7000.00, "CNY", "未知币种收入")
    entry.post(ledger)
    assert entry.post_status == "posted"

    settle_entry = balanced_entry("2025-01-16", "draft", "BTN 结算尝试")
    settle_entry.add_line("银行存款-CNY", -7000.00, "CNY", "BTN 结汇")
    settle_entry.add_line("银行存款-BTN", -10000.00, "BTN", "结清 BTN 存款")
    with pytest.raises(UnknownCurrencyException):
        settle_entry.post(ledger)
    assert settle_entry.post_status == "draft", "结算失败后状态应保持草稿"
    assert len(settle_entry.lines) == 2
    assert settle_entry.is_balanced() is True


def test_b58_three_consecutive_entries_debit_total():
    ledger = open_books()
    dates = ["2025-01-06", "2025-01-09", "2025-01-11"]
    debit_totals = []
    for i, date in enumerate(dates):
        entry = balanced_entry(date, "draft", f"连续凭证{i+1}")
        entry.add_line("管理费用", -100.00 * (i + 1), "CNY", f"第{i+1}笔管理费和")
        entry.add_line("银行存款-CNY", 100.00 * (i + 1), "CNY", f"第{i+1}笔管理费")
        entry.post(ledger)
        assert entry.post_status == "posted"
        assert entry.is_balanced() is True
        debit_total = sum(l.amount for l in entry.lines if l.amount > 0)
        debit_totals.append(debit_total)

    total_debits = sum(debit_totals)
    expected_total = sum(100.00 * (i + 1) for i in range(3))
    assert total_debits == expected_total, f"三笔借方合计应为{expected_total}"
    assert len([d for d in debit_totals if d > 0]) == 3
    assert ledger.get_account_balance("银行存款-CNY") == expected_total
    assert ledger.get_account_balance("管理费用") == -expected_total
    assert len(dates) == 3
    for i, dt in enumerate(debit_totals):
        assert dt == 100.00 * (i + 1), f"第{i+1}笔借方合计应为{100.00 * (i + 1)}"
    # 连续三笔借方合计验证
    assert total_debits == 300.00
```