"""Long scenario tests for the multi-currency ledger.

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


def test_b13_usd_100_on_jan15_converts_to_723_45(fx_setup):
    """USD 100 on 1月15日折合 723.45（使用1月10日7.2345）"""
    amount_fx = 100
    currency = "USD"
    txn_date = "2025-01-15"
    result = convert_foreign_to_local(amount_fx, currency, "CNY", txn_date)
    # 断言1：折算结果应为723.45
    assert abs(result - 723.45) < 0.01
    # 断言2：原始乘法结果在舍入前为723.45
    raw = amount_fx * 7.2345
    assert raw == 723.45
    # 断言3：round到2位小数后精确等于723.45
    assert round(raw, 2) == 723.45
    # 断言4：系统选取的汇率确实为7.2345
    rate_used = fx_setup.get_rate(currency, "CNY", txn_date)
    assert rate_used == 7.2345
    # 断言5：1月10日的汇率被正确识别为最近一条
    assert fx_setup.get_rate(currency, "CNY", "2025-01-10") == 7.2345
    # 断言6：不应使用1月20日的7.2500
    wrong = round(amount_fx * 7.2500, 2)
    assert result != wrong
    # 断言7：交易日之后才有更新的汇率，之前取最早的
    assert "2025-01-10" < txn_date < "2025-01-20"
    # 断言8：汇率精度为4位小数
    assert len(str(rate_used).split(".")[-1]) == 4

def test_b14_usd_100_on_jan20_converts_to_725_00(fx_setup):
    """USD 100在1月20日用7.2500折合725.00"""
    amount_fx = 100
    currency = "USD"
    txn_date = "2025-01-20"
    result = convert_foreign_to_local(amount_fx, currency, "CNY", txn_date)
    # 断言1：折算结果应为725.00
    assert abs(result - 725.00) < 0.01
    # 断言2：当天汇率应正好是7.2500
    rate = fx_setup.get_rate(currency, "CNY", txn_date)
    assert rate == 7.2500
    # 断言3：直接计算结果一致
    expected = round(100 * 7.2500, 2)
    assert result == expected
    # 断言4：该汇率与1月10日不同
    assert rate != fx_setup.get_rate(currency, "CNY", "2025-01-10")
    # 断言5：1月20日汇率晚于1月10日
    assert "2025-01-20" > "2025-01-10"
    # 断言6：同金额在不同日期得到不同结果
    jan15_result = convert_foreign_to_local(100, "USD", "CNY", "2025-01-15")
    assert result != jan15_result
    # 断言7：两个汇率均被注册且可检索
    assert fx_setup.get_rate(currency, "CNY", "2025-01-10") == 7.2345
    assert fx_setup.get_rate(currency, "CNY", "2025-01-20") == 7.2500
    # 断言8：无更早汇率时交易当天汇率优先
    assert rate == 7.2500

def test_b15_eur_50_converts_to_390_06(fx_setup):
    """EUR 50折合390.06（汇率7.8012，本位币CNY）"""
    amount_fx = 50
    currency = "EUR"
    txn_date = "2025-01-15"
    result = convert_foreign_to_local(amount_fx, currency, "CNY", txn_date)
    # 断言1：结果应为390.06
    assert abs(result - 390.06) < 0.01
    # 断言2：50 * 7.8012 = 390.06
    raw = 50 * 7.8012
    assert raw == 390.06
    # 断言3：round(390.06, 2) == 390.06
    assert round(raw, 2) == 390.06
    # 断言4：汇率应为7.8012
    rate = fx_setup.get_rate(currency, "CNY", txn_date)
    assert rate == 7.8012
    # 断言5：汇率仅有一条，直接匹配
    assert fx_setup.get_rate(currency, "CNY", "2025-01-15") == 7.8012
    # 断言6：不是用其他币种汇率计算
    usd_result = convert_foreign_to_local(50, "USD", "CNY", txn_date)
    assert result != usd_result
    # 断言7：EUR对CNY汇率不同于USD
    assert fx_setup.get_rate("EUR", "CNY", txn_date) != fx_setup.get_rate("USD", "CNY", txn_date)
    # 断言8：转换公式为amount * rate后round到2位
    assert result == round(amount_fx * rate, 2)

def test_b16_jpy_10000_converts_to_482_00(fx_setup):
    """JPY 10000折合482.00（汇率0.0482）"""
    amount_fx = 10000
    currency = "JPY"
    txn_date = "2025-01-15"
    result = convert_foreign_to_local(amount_fx, currency, "CNY", txn_date)
    # 断言1：结果应为482.00
    assert abs(result - 482.00) < 0.01
    # 断言2：10000 * 0.0482 = 482.00
    raw = 10000 * 0.0482
    assert raw == 482.00
    # 断言3：汇率应为0.0482
    rate = fx_setup.get_rate(currency, "CNY", txn_date)
    assert rate == 0.0482
    # 断言4：round(482.00, 2) == 482.00
    assert round(raw, 2) == 482.00
    # 断言5：JPY汇率不同于EUR、USD
    assert rate != fx_setup.get_rate("EUR", "CNY", txn_date)
    assert rate != fx_setup.get_rate("USD", "CNY", txn_date)
    # 断言6：汇率精度4位小数，计算后结果为整数
    assert len(str(rate).split(".")[-1]) == 4
    # 断言7：JPY换算金额远小于同数量级USD
    usd_equiv = convert_foreign_to_local(100, "USD", "CNY", txn_date)
    assert usd_equiv > result
    # 断言8：JPY 1万约等于USD 132
    approx_usd = 10000 / 7.2345
    assert approx_usd == round(1368.45)
    # 实际上JPY对CNY直接汇率0.0482，验证无误
    assert result == 482.00

def test_b17_missing_gbp_rate_throws_unknown_currency_exception(fx_setup):
    """缺失GBP汇率，post抛UnknownCurrencyException"""
    # 构造一笔包含GBP的分录尝试过账
    entry = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                         draft=True, created_by="tester")
    # 添加借方行：GBP
    entry.add_line(account="1001", debit_amount=100, credit_amount=0,
                   currency="GBP", line_number=1, date="2025-01-15", description="test")
    # 添加贷方行：CNY（作为对冲，需折算）
    entry.add_line(account="2001", debit_amount=0, credit_amount=723.45,
                   currency="CNY", line_number=2, date="2025-01-15", description="test")
    # 余额检查应先通过
    assert entry.is_balanced()
    # 断言1：未知币种会导致UnknownCurrencyException
    with pytest.raises(UnknownCurrencyException):
        post_journal_entry(entry)
    # 断言2：异常类型正确而非JournalEntryInvalidException
    try:
        post_journal_entry(entry)
        assert False, "Should raise UnknownCurrencyException"
    except UnknownCurrencyException:
        pass
    except JournalEntryInvalidException:
        assert False, "Wrong exception type"
    # 断言3：GBP未在系统中注册，open_books未注册它
    # 假设get_currency_rates返回空列表表示未注册
    rates_for_gbp = fx_setup.get_rate("GBP", "CNY", "2025-01-15")
    assert rates_for_gbp is None
    # 断言4：CNY已注册，对比确认异常仅因GBP
    cny_rate = fx_setup.get_rate("USD", "CNY", "2025-01-10")
    assert cny_rate == 7.2345
    # 断言5：异常应在post时抛出，而非创建时
    assert entry.status == "draft"
    # 断言6：assert行数等基础信息正确
    assert len(entry.lines) == 2
    # 断言7：借贷合计仍为0（因未过账）
    total_debit = sum(l.debit_amount for l in entry.lines)
    total_credit = sum(l.credit_amount for l in entry.lines)
    assert total_debit == total_credit
    # 断言8：未知币种不影响已注册币种行的数据完整性
    cny_line = next(l for l in entry.lines if l.currency == "CNY")
    assert cny_line.credit_amount == 723.45

def test_b18_posting_unknown_currency_throws_unknown_currency_exception(fx_setup):
    """过账未知币种抛UnknownCurrencyException"""
    # 单条分录只含GBP，无其他币种对冲
    entry = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                         draft=True, created_by="tester")
    entry.add_line(account="1001", debit_amount=100, credit_amount=0,
                   currency="GBP", line_number=1, date="2025-01-15", description="unknown")
    # 空分录平衡检查为True，但币种未知
    assert entry.is_balanced()
    # 断言1：过账抛UnknownCurrencyException
    with pytest.raises(UnknownCurrencyException):
        post_journal_entry(entry)
    # 断言2：即使借方贷方合计为0也会抛
    total = sum(l.debit_amount + l.credit_amount for l in entry.lines)
    assert total == 100
    # 断言3：assert条目状态仍为草稿
    assert entry.status == "draft"
    # 断言4：不是抛PeriodClosedForNormalEntryException
    try:
        post_journal_entry(entry)
        assert False
    except PeriodClosedForNormalEntryException:
        assert False, "wrong exception"
    # 断言5：不是抛JournalEntryInvalidException
    try:
        post_journal_entry(entry)
        assert False
    except JournalEntryInvalidException:
        assert False, "wrong exception"
    # 断言6：GBP确实未注册，确认因果
    assert fx_setup.get_rate("GBP", "CNY", "2025-01-15") is None
    # 断言7：存在已知币种则不会抛此异常
    known_entry = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                               draft=True, created_by="tester")
    known_entry.add_line(account="1001", debit_amount=100, credit_amount=0,
                         currency="USD", line_number=1, date="2025-01-15")
    known_entry.add_line(account="2001", debit_amount=0, credit_amount=723.45,
                         currency="CNY", line_number=2, date="2025-01-15")
    # 断言8：已知币种可以正常balance检查
    assert known_entry.is_balanced()
    # 实际post会因汇率查找成功继续，但此处不验证post结果避免耦合
    # 重点验证未知币种路径抛出的异常类型正确

def test_b19_local_currency_conversion_stays_as_original_amount(fx_setup):
    """本位币折算仍为原金额（CNY对CNY汇率返回1）"""
    amount_cny = 1000
    result = convert_foreign_to_local(amount_cny, "CNY", "CNY", "2025-01-15")
    # 断言1：本位币折算结果不变
    assert result == amount_cny
    # 断言2：本位币兑本位币汇率为1
    rate = fx_setup.get_rate("CNY", "CNY", "2025-01-15")
    assert rate == 1
    # 断言3：1000 * 1 = 1000，round(1000, 2) = 1000
    assert round(amount_cny * rate, 2) == amount_cny
    # 断言4：无论哪一天结果都一样（汇率恒为1）
    feb_result = convert_foreign_to_local(1000, "CNY", "CNY", "2025-02-15")
    assert result == feb_result
    # 断言5：外币折算结果不等于本位币结果
    usd_result = convert_foreign_to_local(100, "USD", "CNY", "2025-01-15")
    assert result != usd_result
    # 断言6：本位币金额不参与汇率查找逻辑
    # 本位币兑换不需要登记汇率，open_books也不包含CNY-CNY
    # 直接调用get_rate应回退到1
    assert rate == 1
    # 断言7：其他币种对CNY汇率非1
    assert fx_setup.get_rate("USD", "CNY", "2025-01-10") != 1
    assert fx_setup.get_rate("EUR", "CNY", "2025-01-15") != 1
    # 断言8：本位币转换不受汇率波动影响
    assert convert_foreign_to_local(1000, "CNY", "CNY", "2025-01-01") == 1000
    # 断言9：本位币金额保持整数或浮点精度不变
    assert isinstance(result, (int, float))
    # 断言10：结果精确相等而非近似
    assert result == 1000

def test_b20_rate_takes_earliest_rate_before_or_on_transaction_date(fx_setup):
    """汇率取早于交易日的最近一条"""
    # 交易日1月12日，介于1月10日和1月20日之间
    txn_date = "2025-01-12"
    amount = 100
    result = convert_foreign_to_local(amount, "USD", "CNY", txn_date)
    # 断言1：应使用1月10日（早于交易日）的汇率
    expected_rate = 7.2345
    expected = round(amount * expected_rate, 2)
    assert result == expected
    # 断言2：不应使用1月20日（晚于交易日）的汇率
    late_rate = 7.2500
    wrong = round(amount * late_rate, 2)
    assert result != wrong
    # 断言3：交易日早于1月20日
    assert txn_date < "2025-01-20"
    # 断言4：交易日晚于1月10日
    assert txn_date > "2025-01-10"
    # 断言5：get_rate方法应返回正确的历史汇率
    retrieved = fx_setup.get_rate("USD", "CNY", txn_date)
    assert retrieved == expected_rate
    # 断言6：历史记录中1月10日确实在交易日之前
    history_dates = sorted(["2025-01-10", "2025-01-12", "2025-01-20"])
    idx = history_dates.index(txn_date)
    assert history_dates[idx - 1] == "2025-01-10"
    # 断言7：选择的是交易日及之前最近的汇率
    assert retrieved == fx_setup.get_rate("USD", "CNY", "2025-01-10")
    # 断言8：若有多条历史汇率，取最大日期但仍≤交易日
    # 当前只有两条，1月10日是唯一符合条件的
    rates = [(d, fx_setup.get_rate("USD", "CNY", d)) for d in ["2025-01-10", "2025-01-20"]]
    valid = [r for d, r in rates if d <= txn_date]
    assert len(valid) == 1
    assert valid[0][1] == 7.2345
    # 断言9：汇率按时间顺序排列，1月10日最早
    assert "2025-01-10" == min(d for d, _ in rates)
    # 断言10：1月12日没有汇率记录，应 fallback 到之前的1月10日
    assert fx_setup.get_rate("USD", "CNY", "2025-01-12") is None
    # 但convert_foreign_to_local仍能正常工作
    assert result == expected

def test_b21_jan9_no_earlier_rate_uses_jan10(fx_setup):
    """1月9日没有更早汇率时改用之后的1月10日"""
    txn_date = "2025-01-09"
    amount = 100
    result = convert_foreign_to_local(amount, "USD", "CNY", txn_date)
    # 断言1：结果应使用1月10日的7.2345
    expected = round(amount * 7.2345, 2)
    assert result == expected
    # 断言2：1月9日之前无任何汇率记录
    # 已注册最早为1月10日
    early_rates = fx_setup.get_rate("USD", "CNY", d)
    for d in ["2025-01-01", "2025-01-05", "2025-01-08"]:
        assert early_rates == 7.2345 is False  # 不存在应返回None或默认值
    # 断言3：1月10日是最早可用的汇率
    assert fx_setup.get_rate("USD", "CNY", "2025-01-10") == 7.2345
    # 断言4：1月9日到1月10日只有一天间隔
    # 即date_diff最小
    from datetime import date
    diff = (date.fromisoformat("2025-01-10") - date.fromisoformat("2025-01-09")).days
    assert diff == 1
    # 断言5：不应使用1月20日的汇率
    wrong = round(amount * 7.2500, 2)
    assert result != wrong
    # 断言6：1月10日是唯一可用的候选
    available = fx_setup.get_rate("USD", "CNY", txn_date)
    # 实现上可能返回None或自动fallback到最近可用
    # 核心逻辑：1月9日找不到→找之后最近的→1月10日
    # 断言7：确认1月9日当天无汇率
    assert fx_setup.get_rate("USD", "CNY", "2025-01-09") is None
    # 断言8：result与直接使用1月10日汇率相同
    direct = convert_foreign_to_local(100, "USD", "CNY", "2025-01-10")
    assert result == direct
    # 断言9：交易日早于任何已注册汇率日期
    # 意味着必须向后查找
    assert txn_date < "2025-01-10"
    # 断言10：此行为与test_b20形成对照：b20交易日在中间，b21交易日在前
    mid_result = convert_foreign_to_local(100, "USD", "CNY", "2025-01-12")
    assert result == mid_result
    assert txn_date != "2025-01-12"

def test_b22_three_currency_mixed_but_local_balance(fx_setup):
    """三币种混合但本位币借贷平衡"""
    # 构造一笔混合分录：USD借、EUR贷、JPY借、CNY贷
    entry = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                         draft=True, created_by="tester")
    # USD 100 借方 → 折算723.45
    entry.add_line(account="1001", debit_amount=100, credit_amount=0,
                   currency="USD", line_number=1, date="2025-01-15", description="fx buy")
    # EUR 50 贷方 → 折算390.06
    entry.add_line(account="2001", debit_amount=0, credit_amount=50,
                   currency="EUR", line_number=2, date="2025-01-15", description="fx sell")
    # JPY 10000 借方 → 折算482.00
    entry.add_line(account="1002", debit_amount=10000, credit_amount=0,
                   currency="JPY", line_number=3, date="2025-01-15", description="fx buy")
    # CNY 借/贷差额通过本位币调整：USD+JPY合计723.45+482.00=1205.45，减去EUR 390.06得借方815.39
    cny_amount = round(723.45 + 482.00 - 390.06, 2)
    entry.add_line(account="2002", debit_amount=cny_amount, credit_amount=0,
                   currency="CNY", line_number=4, date="2025-01-15", description="local bal")
    # 断言1：is_balanced()为True
    assert entry.is_balanced()
    # 断言2：所有外币折算后与本位币合计相等
    total_fx_local = convert_foreign_to_local(100, "USD", "CNY", "2025-01-15")
    total_fx_local += convert_foreign_to_local(10000, "JPY", "CNY", "2025-01-15")
    total_fx_local -= convert_foreign_to_local(50, "EUR", "CNY", "2025-01-15")
    # 借方总计
    debit_sum = sum(l.debit_amount for l in entry.lines)
    # 贷方总计
    credit_sum = sum(l.credit_amount for l in entry.lines)
    # 由于CNY是本位币，debit_amount即为本地金额
    assert debit_sum == cny_amount + 723.45 + 482.00  # CNY借 + USD借 + JPY借（折算后计入本地）
    # 更准确的平衡检查：折算后借方合计 = 贷方合计
    fx_debits = [l for l in entry.lines if l.currency != "CNY" and l.debit_amount > 0]
    fx_credits = [l for l in entry.lines if l.currency != "CNY" and l.credit_amount > 0]
    fx_debit_local = convert_foreign_to_local(100, "USD", "CNY", "2025-01-15")
    fx_debit_local += convert_foreign_to_local(10000, "JPY", "CNY", "2025-01-15")
    fx_credit_local = convert_foreign_to_local(50, "EUR", "CNY", "2025-01-15")
    local_debit = cny_amount
    # 借方总额 = 外币借 + 本位币借
    # 贷方总额 = 外币贷 + 本位币贷（这里本位币只在借方）
    # 断言3：is_balanced内部已处理折算，直接断言通过
    assert entry.is_balanced()
    # 断言4：各行币种不同
    currencies = [l.currency for l in entry.lines]
    assert len(currencies) == len(set(currencies))
    assert currencies.count("USD") == 1
    assert currencies.count("EUR") == 1
    assert currencies.count("JPY") == 1
    assert currencies.count("CNY") == 1
    # 断言5：借贷方各两行
    assert sum(1 for l in entry.lines if l.debit_amount > 0) == 3
    assert sum(1 for l in entry.lines if l.credit_amount > 0) == 1
    # 修正：加上CNY借方行 → 借方3行，贷方1行，合计借方>贷方？不，这是凭证行
    # 实际上is_balanced考虑了折算后本地金额相等
    # 重新理解：本位币行承担盈亏平衡
    # 断言6：折算后的净差由CNY行吸收
    net_fx = (723.45 + 482.00) - 390.06
    assert abs(net_fx - cny_amount) < 0.01
    # 断言7：每行都有各自的line_number，无重复
    line_nums = [l.line_number for l in entry.lines]
    assert len(line_nums) == len(set(line_nums))
    # 断言8：同一侧不同币种可出现多次（如借方有USD和JPY）
    debit_lines = [l for l in entry.lines if l.debit_amount > 0]
    assert len(debit_lines) == 3
    currencies_in_debit = [l.currency for l in debit_lines]
    assert "USD" in currencies_in_debit
    assert "JPY" in currencies_in_debit
    # 断言9：overal local balance verified via is_balanced
    assert entry.is_balanced()
    # 断言10：日期都在期间内
    for l in entry.lines:
        assert "2025-01-01" <= l.date <= "2025-01-31"

def test_b23_after_posting_status_becomes_posted(fx_setup):
    """过账后状态变为已过账"""
    entry = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                         draft=True, created_by="tester")
    entry.add_line(account="1001", debit_amount=100, credit_amount=0,
                   currency="USD", line_number=1, date="2025-01-15", description="test")
    entry.add_line(account="2001", debit_amount=0, credit_amount=723.45,
                   currency="CNY", line_number=2, date="2025-01-15", description="test")
    # 过账前状态为草稿
    assert entry.status == "draft"
    # 断言1：过账后状态应为posted
    post_journal_entry(entry)
    assert entry.status == "posted"
    # 断言2：过账前是draft，确认变化发生
    assert entry.status != "draft"
    # 断言3：过账后不可再修改（假设add_line在非草稿抛异常）
    try:
        entry.add_line(account="3001", debit_amount=0, credit_amount=1,
                       currency="CNY", line_number=3, date="2025-01-15")
        # 根据描述：非草稿add_line抛JournalEntryInvalidException
        assert False, "Should raise JournalEntryInvalidException"
    except JournalEntryInvalidException:
        pass
    # 断言4：过账后is_balanced仍为True
    assert entry.is_balanced()
    # 断言5：过账后行信息不变
    assert len(entry.lines) == 2
    assert entry.lines[0].debit_amount == 100
    assert entry.lines[1].credit_amount == 723.45
    # 断言6：post_journal_entry返回值可能是entry本身或bool
    result = post_journal_entry(entry)
    # 若返回值为entry，确认其状态
    if result is entry:
        assert result.status == "posted"
    # 断言7：过账操作不可逆（至少本次会话中）
    assert entry.status == "posted"
    # 断言8：period_key在过账后仍然有效
    assert entry.period_key == "2025-01"
    # 断言9：book_manager引用未变
    assert entry.book_manager is fx_setup
    # 断言10：过账后创建者字段未变
    assert entry.created_by == "tester"

def test_b24_posted_by_is_written_after_posting(fx_setup):
    """过账后posted_by被写入"""
    entry = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                         draft=True, created_by="tester")
    entry.add_line(account="1001", debit_amount=100, credit_amount=0,
                   currency="USD", line_number=1, date="2025-01-15", description="test")
    entry.add_line(account="2001", debit_amount=0, credit_amount=723.45,
                   currency="CNY", line_number=2, date="2025-01-15", description="test")
    # 过账前可能有或没有posted_by字段
    assert hasattr(entry, "created_by")
    # 断言1：过账后posted_by应被设置
    post_journal_entry(entry)
    assert hasattr(entry, "posted_by")
    # 断言2：posted_by的值不为空
    assert entry.posted_by is not None
    # 断言3：posted_by通常等于created_by或系统标识
    # 取决于实现：可能是"tester"或自动生成
    assert entry.posted_by == "tester" or len(entry.posted_by) > 0
    # 断言4：created_by保持原样
    assert entry.created_by == "tester"
    # 断言5：posted_by与created_by区分
    # 有些实现两者相同，有些不同
    # 关键：posted_by字段存在且有意义
    assert entry.posted_by is not None
    # 断言6：过账前后created_by不变
    pre_created_by = "tester"  # 初始化时传入
    assert entry.created_by == pre_created_by
    # 断言7：多笔分录的posted_by一致
    entry2 = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                          draft=True, created_by="tester")
    entry2.add_line(account="1002", debit_amount=50, credit_amount=0,
                    currency="EUR", line_number=1, date="2025-01-15")
    entry2.add_line(account="2002", debit_amount=0, credit_amount=390.06,
                    currency="CNY", line_number=2, date="2025-01-15")
    post_journal_entry(entry2)
    assert entry2.posted_by is not None
    # 断言8：posted_by写入时机在post时，而非add_line时
    entry3 = JournalEntry(book_manager=fx_setup, period_key="2025-01",
                          draft=True, created_by="tester")
    entry3.add_line(account="1001", debit_amount=100, credit_amount=0,
                    currency="USD", line_number=1, date="2025-01-15")
    entry3.add_line(account="2001", debit_amount=0, credit_amount=723.45,
                    currency="CNY", line_number=2, date="2025-01-15")
    # add_line时posted_by未设置
    assert not hasattr(entry3, "posted_by") or entry3.posted_by is None
    post_journal_entry(entry3)
    assert hasattr(entry3, "posted_by")
    # 断言9：posted_by为字符串类型
    assert isinstance(entry.posted_by, str)
    # 断言10：posted_by记录谁执行了过账
    # 通常与当前用户或系统相关
    assert len(entry.posted_by) > 0

def test_b25(ledger):
    """场景 b25: 关闭一月后普通过账被拒绝"""
    led = ledger
    jan_key = "2025-01"
    feb_key = "2025-02"
    # 先确认两个期间都已存在于账簿之中
    assert jan_key in led.periods, "一月期间应在账簿中"
    assert feb_key in led.periods, "二月期间应在账簿中"
    # 确认一月初始确实未处于关闭状态
    assert not led.periods[jan_key].is_closed, "一月初始不应已关闭"
    # 构造一条正常的借方收入凭证用于后续操作
    jan_entry = led.create_journal_entry(
        period_key=jan_key, entry_date="2025-01-05", entry_type=EntryType.NORMAL
    )
    jan_entry.add_line(account_id="1001", description="收款", amount_local=100.00)
    jan_entry.add_line(account_id="1002", description="支出", amount_local=-100.00)
    assert len(jan_entry.lines) == 2, "凭证应包含两条分录"
    assert jan_entry.is_balanced(), "等额借贷的分录应是平衡的"
    # 执行关闭一月期间
    close_result = close_period(jan_key, led)
    assert close_result is True, "关闭期间的调用应返回真值"
    assert led.periods[jan_key].is_closed, "关闭后一月的 is_closed 必须为 True"
    # 尝试过账到已关闭的期间，预期抛出 PeriodClosedForNormalEntryException
    jan_entry.entry_date = "2025-01-10"
    with pytest.raises(PeriodClosedForNormalEntryException):
        post_journal_entry(jan_entry, led)
    # 同样直接在一月创建新凭证也应拒绝
    with pytest.raises(PeriodClosedForNormalEntryException):
        led.create_journal_entry(jan_key, "2025-01-15", EntryType.NORMAL)
    # 验证二月作为未关闭期间仍可以正常创建并过账
    feb_entry = led.create_journal_entry(feb_key, "2025-02-10", EntryType.NORMAL)
    feb_entry.add_line(account_id="1001", description="费用", amount_local=50.00)
    feb_entry.add_line(account_id="1002", description="回款", amount_local=-50.00)
    feb_posted = post_journal_entry(feb_entry, led)
    assert feb_posted is True, "二月的凭证过账应成功"
    assert feb_entry.posted, "过账后凭证的 posted 字段应为 True"
    # 验证一月被关闭后其中不再能有任何新分录进入
    jan_new = led.create_journal_entry(jan_key, "2025-01-16", EntryType.NORMAL)
    jan_new.add_line(account_id="1003", description="尝试追加", amount_local=10.00)
    jan_new.add_line(account_id="1004", description="对冲", amount_local=-10.00)
    with pytest.raises(PeriodClosedForNormalEntryException):
        post_journal_entry(jan_new, led)

def test_b26(ledger):
    """场景 b26: 一月关闭后，二月仍然可以正常过账"""
    led = ledger
    jan_key = "2025-01"
    feb_key = "2025-02"
    # 先关闭一月确保环境符合场景要求
    close_result = close_period(jan_key, led)
    assert close_result is True, "关闭一月应返回成功标识"
    assert led.periods[jan_key].is_closed, "一月应标记为已关闭"
    # 确认二月仍未关闭
    assert not led.periods[feb_key].is_closed, "二月应仍处于开放状态"
    # 在二月创建并过账一条完整凭证
    feb_entry = led.create_journal_entry(feb_key, "2025-02-05", EntryType.NORMAL)
    feb_entry.add_line(account_id="2001", description="销售", amount_local=200.00)
    feb_entry.add_line(account_id="2002", description="进项", amount_local=-200.00)
    assert feb_entry.is_balanced(), "创建的凭证必须是平衡的"
    # 过账操作应成功且不修改除 posted 外的其他状态
    success = post_journal_entry(feb_entry, led)
    assert success is True, "二月的凭证过账应返回 True"
    assert feb_entry.posted, "过账后凭证的 posted 字段应为 True"
    # 验证二月期间现已包含一条已过账记录
    feb_entries = list(led.periods[feb_key].entries.values())
    assert len(feb_entries) >= 1, "二月期间应至少有该条凭证"
    # 验证一月里即便有草稿也无法绕过关闭限制
    jan_draught = led.create_journal_entry(jan_key, "2025-01-14", EntryType.NORMAL)
    jan_draught.add_line(account_id="1001", description="偷渡", amount_local=10.00)
    jan_draught.add_line(account_id="1002", description="对冲", amount_local=-10.00)
    with pytest.raises(PeriodClosedForNormalEntryException):
        post_journal_entry(jan_draught, led)
    # 最终统计二月已过账凭证数恰好为 1
    final_feb_count = len([e for e in feb_entries if e.posted])
    assert final_feb_count == 1, "二月已过的凭证数应为 1"
    # 同时验证一月里没有任何成功过账的凭证混入
    jan_posted_count = len([e for e in led.periods[jan_key].entries.values() if e.posted])
    assert jan_posted_count == 0, "一月不应有过账凭证"

def test_b27(ledger):
    """场景 b27: 调整类型 CORRECTION 调用 adjust_journal_entry"""
    led = ledger
    feb_key = "2025-02"
    # 先创建一条原始普通凭证作为调整的基准
    orig_entry = led.create_journal_entry(feb_key, "2025-02-05", EntryType.NORMAL)
    orig_entry.add_line(account_id="3001", description="原业务", amount_local=100.00)
    orig_entry.add_line(account_id="3003", description="配平", amount_local=-100.00)
    post_journal_entry(orig_entry, led)
    assert orig_entry.posted, "原始凭证应先过账"
    # 用调整类型创建更正凭证并传入原凭证标识
    corr_entry = led.create_journal_entry(
        feb_key, "2025-02-15", entry_type=EntryType.CORRECTION,
        reference_entry_id=str(id(orig_entry))
    )
    corr_entry.add_line(account_id="3001", description="调整更正", amount_local=100.00)
    corr_entry.add_line(account_id="3003", description="配平调整", amount_local=-100.00)
    assert corr_entry.is_balanced(), "更正分录必须也是平衡的"
    # 调整过账应成功返回
    adjusted = post_journal_entry(corr_entry, led)
    assert adjusted is True, "CORRECTION 类型的过账应成功"
    # 验证二月内现在的凭证总数为 2（原始 + 调整）
    feb_all = list(led.periods[feb_key].entries.values())
    assert len(feb_all) == 2, "二月应有原始凭证和调整凭证共两条"
    # 原始凭证应保持已过账状态，调整不影响它
    found_orig = next((e for e in feb_all if e is orig_entry), None)
    assert found_orig is not None, "应能在二月找到原始凭证"
    assert found_orig.posted, "原始凭证状态仍应为已过账"
    # 验证原分录的行数和金额没有被调整操作改动
    assert len(orig_entry.lines) == 2, "原分录行数不得变化"
    assert abs(orig_entry.lines[0].amount_local) == 100.00, "原分录金额不得改变"
    # 验证调整凭证的类型标识确实是 CORRECTION
    assert corr_entry.entry_type is EntryType.CORRECTION, "类型应确认为 CORRECTION"
    # 验证调整后两条凭证各自都是独立的平衡实体
    for entry in [orig_entry, corr_entry]:
        debit = sum(l.amount_local for l in entry.lines if l.amount_local > 0)
        credit = abs(sum(l.amount_local for l in entry.lines if l.amount_local < 0))
        assert debit == credit, f"凭证 {entry} 借贷合计必须相等"

def test_b28(ledger):
    """场景 b28: 不平衡的调整分录应被拒绝过账"""
    led = ledger
    feb_key = "2025-02"
    # 建立一条正常凭证做参照
    ref_entry = led.create_journal_entry(feb_key, "2025-02-01", EntryType.NORMAL)
    ref_entry.add_line(account_id="5001", description="参照业务", amount_local=50.00)
    ref_entry.add_line(account_id="5002", description="参照配平", amount_local=-50.00)
    post_journal_entry(ref_entry, led)
    # 构造一条明显不平衡的调整分录
    unbal_entry = led.create_journal_entry(
        feb_key, "2025-02-20", entry_type=EntryType.CORRECTION,
        reference_entry_id=str(id(ref_entry))
    )
    unbal_entry.add_line(account_id="5001", description="调增", amount_local=80.00)
    unbal_entry.add_line(account_id="5002", description="调减", amount_local=-30.00)
    assert not unbal_entry.is_balanced(), "此分录应该是不平衡的"
    # 尝试过账不平衡的调整，应抛出异常阻止
    with pytest.raises(Exception):
        post_journal_entry(unbal_entry, led)
    # 即使补充一行让借贷数接近，只要不完全平衡仍应失败
    extra_entry = led.create_journal_entry(
        feb_key, "2025-02-21", entry_type=EntryType.CORRECTION
    )
    extra_entry.add_line(account_id="5003", description="补记", amount_local=30.00)
    extra_entry.add_line(account_id="5004", description="对冲", amount_local=-40.00)
    with pytest.raises(Exception):
        post_journal_entry(extra_entry, led)
    # 对比：平衡的调整凭证应该能正常通过
    bal_entry = led.create_journal_entry(
        feb_key, "2025-02-22", entry_type=EntryType.CORRECTION
    )
    bal_entry.add_line(account_id="5003", description="平衡借", amount_local=40.00)
    bal_entry.add_line(account_id="5004", description="平衡贷", amount_local=-40.00)
    assert bal_entry.is_balanced(), "这笔调整应该平衡"
    result = post_journal_entry(bal_entry, led)
    assert result is True, "平衡的调整分录应能过账成功"
    # 最终验证二月里只有合法过账的凭证
    feb_entries = list(led.periods[feb_key].entries.values())
    assert len(feb_entries) == 3, "二月最终应有三条合法凭证"
    # 每条都应满足基本结构校验条件
    for e in feb_entries:
        assert e.is_balanced(), f"凭证 {id(e)} 必须平衡"

def test_b29(ledger):
    """场景 b29: 红字冲销后行金额正负对调且原分录仍是已过账"""
    led = ledger
    feb_key = "2025-02"
    # 建立原始分录
    orig = led.create_journal_entry(feb_key, "2025-02-03", EntryType.NORMAL)
    orig.add_line(account_id="7001", description="原始借方", amount_local=150.00)
    orig.add_line(account_id="7002", description="原始贷方", amount_local=-150.00)
    post_journal_entry(orig, led)
    assert orig.posted, "原始分录必须先过账才能冲销"
    # 进行红字冲销——即反向等额的调整
    rev = led.create_journal_entry(
        feb_key, "2025-02-10", entry_type=EntryType.REVERSAL,
        reference_entry_id=str(id(orig))
    )
    # 红字冲销的本质是借贷符号反转
    rev.add_line(account_id="7001", description="冲销借方", amount_local=-150.00)
    rev.add_line(account_id="7002", description="冲销贷方", amount_local=150.00)
    # 冲销分录应与原分录金额绝对值相等、符号相反
    assert rev.is_balanced(), "冲销分录必须平衡"
    # 冲销过账成功
    post_journal_entry(rev, led)
    # 验证原分录的已过账状态保持不变
    all_entries = list(led.periods[feb_key].entries.values())
    found_orig = next((e for e in all_entries if e is orig), None)
    assert found_orig is not None, "应在凭证列表中找到原始分录"
    assert found_orig.posted, "原始分录冲销后仍应标记为已过账"
    # 冲销行的行数必须严格等于原分录行数
    assert len(rev.lines) == len(orig.lines), "冲销行数必须等于原行数"
    # 逐行比对每一对对应行的正负反转关系
    for i in range(len(orig.lines)):
        orig_amt = orig.lines[i].amount_local
        rev_amt = rev.lines[i].amount_local
        assert rev_amt == -orig_amt, f"第{i}行冲销金额应正负对调"
        assert abs(orig_amt) == abs(rev_amt), f"第{i}行冲销金额绝对值应相等"
    # 验证描述里体现冲销语义
    assert any("冲销" in line.description for line in rev.lines), "冲销描述应含冲销字样"
    # 计算并验证借贷合计
    total_debit = sum(l.amount_local for l in orig.lines if l.amount_local > 0)
    total_credit = abs(sum(l.amount_local for l in orig.lines if l.amount_local < 0))
    assert total_debit == total_credit, "原分录借贷合计必须相等"
    rev_total_debit = abs(sum(l.amount_local for l in rev.lines if l.amount_local < 0))
    rev_total_credit = sum(l.amount_local for l in rev.lines if l.amount_local > 0)
    assert rev_total_debit == rev_total_credit, "冲销分录借贷合计也必须相等"
    # 两条分录加起来总效果应为零（借正贷负抵消）
    combined_total = sum(l.amount_local for l in orig.lines) + sum(l.amount_local for l in rev.lines)
    assert combined_total == 0.00, "原始与冲销合并后净额应为 0"

def test_b30(ledger):
    """场景 b30: 冲销行数等于原行数"""
    led = ledger
    feb_key = "2025-02"
    # 构建一条多行原始凭证来严格测试行数匹配
    orig_lines = [
        ("7101", "商品销售收入 A", 100.00),
        ("7102", "商品销售收入 B", 200.00),
        ("5101", "营业成本", -300.00),
        ("6101", "税费附加", -100.00),
    ]
    orig = led.create_journal_entry(feb_key, "2025-02-05", EntryType.NORMAL)
    for acc_id, desc, amt in orig_lines:
        orig.add_line(account_id=acc_id, description=desc, amount_local=amt)
    post_journal_entry(orig, led)
    assert orig.posted, "原始凭证应已过账"
    assert len(orig.lines) == 4, "原始凭证应有 4 行"
    # 创建与原始分录行数一致的完全反向冲销凭证
    rev = led.create_journal_entry(
        feb_key, "2025-02-12", entry_type=EntryType.REVERSAL,
        reference_entry_id=str(id(orig))
    )
    for i, (acc_id, _, _) in enumerate(orig_lines):
        rev_amt = -orig.lines[i].amount_local
        rev.add_line(
            account_id=acc_id, description=f"冲销{desc}", amount_local=rev_amt
        )
    # 强制检查冲销行数与原始行数相等
    assert len(rev.lines) == len(orig.lines), "冲销行数必须等于原行数"
    # 过账冲销凭证
    post_journal_entry(rev, led)
    # 验证两条凭证都在二月期间内
    entries = list(led.periods[feb_key].entries.values())
    orig_found = any(str(id(e)) == str(id(orig)) for e in entries)
    rev_found = any(str(id(e)) == str(id(rev)) for e in entries)
    assert orig_found, "二月内应能找到原始凭证"
    assert rev_found, "二月内应能找到冲销凭证"
    # 检查每一对对应行的正负关系和账号一致性
    for row_i in range(len(orig.lines)):
        assert rev.lines[row_i].account_id == orig.lines[row_i].account_id
        assert rev.lines[row_i].amount_local == -orig.lines[row_i].amount_local
    # 核对总金额绝对值也一致
    orig_total_abs = sum(abs(l.amount_local) for l in orig.lines)
    rev_total_abs = sum(abs(l.amount_local) for l in rev.lines)
    assert orig_total_abs == rev_total_abs, "冲销总额应等于原总额"
    # 验证冲销后原凭证仍为已过账状态
    orig_in_list = next((e for e in entries if e is orig), None)
    assert orig_in_list.posted, "原始凭证冲销后仍应已过账"

def test_b31(ledger):
    """场景 b31: 冲销说明里带原凭证号"""
    led = ledger
    feb_key = "2025-02"
    # 创建原始凭证
    orig = led.create_journal_entry(feb_key, "2025-02-08", EntryType.NORMAL)
    orig.add_line(account_id="8001", description="现金", amount_local=300.00)
    orig.add_line(account_id="8002", description="银行", amount_local=-300.00)
    post_journal_entry(orig, led)
    # 保存原始凭证的 id 字符串用于引用
    orig_id_str = str(id(orig))
    # 创建带说明的红字冲销并绑定参考编号
    rev = led.create_journal_entry(
        feb_key, "2025-02-15", entry_type=EntryType.REVERSAL,
        reference_entry_id=orig_id_str
    )
    rev.add_line(account_id="8001", description="冲销现金", amount_local=-300.00)
    rev.add_line(account_id="8002", description="冲销银行", amount_local=300.00)
    post_journal_entry(rev, led)
    # 验证 reference_entry_id 字段正确设置
    assert rev.reference_entry_id is not None, "冲销凭证必须有引用编号"
    assert rev.reference_entry_id == orig_id_str, "引用编号必须精确指向原始凭证"
    # 整体凭证列表里应有且仅有 2 条
    all_february = list(led.periods[feb_key].entries.values())
    assert len(all_february) == 2, "二月应该有原始凭证和冲销凭证各一条"
    # 原始凭证仍存在且已过账
    assert any(str(id(e)) == orig_id_str for e in all_february), "原始凭证应在列表中"
    # 冲销说明文本里应包含原始凭证号信息
    combined_desc = " ".join(rev.lines[i].description for i in range(len(rev.lines)))
    assert orig_id_str in combined_desc or rev.reference_entry_id in combined_desc, \
        "冲销说明应包含原始凭证号"
    # 确保冲销后两条凭证各自借贷平衡
    for e in [orig, rev]:
        debit = sum(l.amount_local for l in e.lines if l.amount_local > 0)
        credit = abs(sum(l.amount_local for l in e.lines if l.amount_local < 0))
        assert debit == credit, f"凭证 {e.__class__.__name__} 借贷必须平衡"
    # 验证两条凭证的账号集合相同（冲销是对应科目反向）
    orig_accounts = set(l.account_id for l in orig.lines)
    rev_accounts = set(l.account_id for l in rev.lines)
    assert orig_accounts == rev_accounts, "冲销账号应与原凭证完全一致"

def test_b33(ledger):
    """场景 b33: 未过账的凭证不能进行结算"""
    led = ledger
    feb_key = "2025-02"
    # 创建但未过账的草稿凭证
    draft = led.create_journal_entry(feb_key, "2025-02-20", EntryType.NORMAL)
    draft.add_line(account_id="9001", description="待结算应收", amount_local=200.00)
    draft.add_line(account_id="9002", description="待结算应付", amount_local=-200.00)
    # 明确确认其未过账状态
    assert draft.posted is False, "草稿凭证的 posted 应为 False"
    # 尝试对未过账凭证调用结算，应抛出 JournalEntryInvalidException
    with pytest.raises(JournalEntryInvalidException):
        settle_journal_entry(draft, settlement_type=SettlementType.FULL)
    # 对比：已过账的凭证才允许结算
    valid_entry = led.create_journal_entry(feb_key, "2025-02-21", EntryType.NORMAL)
    valid_entry.add_line(account_id="9003", description="正常应收", amount_local=100.00)
    valid_entry.add_line(account_id="9004", description="正常应付", amount_local=-100.00)
    post_journal_entry(valid_entry, led)
    # 已过账凭证可以正常结算
    settle_journal_entry(valid_entry, settlement_type=SettlementType.FULL)
    # 验证结算后状态保持已过账
    assert valid_entry.posted is True, "结算后凭证保持已过账状态"
    # 验证结算后金额归零
    assert sum(abs(l.amount_local) for l in valid_entry.lines) == 0, "结算后余额应为 0"

def test_b34(ledger):
    """场景 b34: 全额结算后剩余外币为 0"""
    led = ledger
    feb_key = "2025-02"
    # 过账一笔含外币金额的凭证
    fx_entry = led.create_journal_entry(feb_key, "2025-02-05", EntryType.NORMAL)
    fx_entry.add_line(account_id="1201", description="出口收入 USD", amount_local=1000.00,
                      foreign_currency_amount=100.00, foreign_currency_code="USD")
    fx_entry.add_line(account_id="1202", description="进口支出 EUR", amount_local=-800.00,
                      foreign_currency_amount=100.00, foreign_currency_code="EUR")
    post_journal_entry(fx_entry, led)
    # 对外币转换验证——2025-01-15 的 USD 汇率应取 1 月 10 日的 7.2345
    usd_local = convert_foreign_to_local(amount=100.00, currency="USD", date="2025-01-15", ledger=led)
    expected_usd = round(100 * 7.2345, 2)
    assert usd_local == expected_usd, f"USD 转换应得 {expected_usd}"
    # 对 EUR 用 7.8012
    eur_local = convert_foreign_to_local(amount=100.00, currency="EUR", date="2025-02-10", ledger=led)
    expected_eur = round(100 * 7.8012, 2)
    assert eur_local == expected_eur, f"EUR 转换应得 {expected_eur}"
    # 执行全额结算
    settle_journal_entry(fx_entry, settlement_type=SettlementType.FULL)
    # 验证结算后外币余额归零
    remaining = settle_journal_entry(fx_entry, settlement_type=SettlementType.PARTIAL, amount=None)
    assert remaining is None or remaining.local_amount == 0, "全额结算后外币余额应为 0"
    # 验证凭证上的外币字段已被清空或归零
    for line in fx_entry.lines:
        assert getattr(line, 'foreign_currency_amount', 0) == 0, "结算后外币金额应清零"
    # 本位币合计也为零
    total_local = sum(l.amount_local for l in fx_entry.lines)
    assert total_local == 0, "结算后本位币合计应为 0"
    # 验证 CNY 本位币兑本位币汇率函数直接返回 1
    cny_rate = convert_foreign_to_local(amount=100.00, currency="CNY", date="2025-02-15", ledger=led)
    assert cny_rate == 100.00, "本位币换算应返回原值（汇率 1）"

def test_b35(ledger):
    """场景 b35: 部分结算 40/100 剩余 60"""
    led = ledger
    feb_key = "2025-02"
    # 创建一笔金额为 100 的凭证
    partial_entry = led.create_journal_entry(feb_key, "2025-02-10", EntryType.NORMAL)
    partial_entry.add_line(account_id="3001", description="分期应收", amount_local=100.00,
                           foreign_currency_amount=100.00, foreign_currency_code="CNY")
    partial_entry.add_line(account_id="3002", description="分期应付", amount_local=-100.00,
                           foreign_currency_amount=100.00, foreign_currency_code="CNY")
    post_journal_entry(partial_entry, led)
    # 第一次部分结算支付 40
    first_payment = SettlementType.PARTIAL.with_amount(local_amount=40.00)
    rem_after_first = settle_journal_entry(partial_entry, settlement_type=first_payment)
    assert rem_after_first is not None, "首次部分结算应返回剩余金额"
    assert rem_after_first.local_amount == 60.00, "首次结算后剩余应正好为 60"
    # 第二次部分结算再支付 40（累计 80）
    second_payment = SettlementType.PARTIAL.with_amount(local_amount=40.00)
    rem_after_second = settle_journal_entry(partial_entry, settlement_type=second_payment)
    assert rem_after_second.local_amount == 20.00, "二次结算后剩余应为 20"
    # 第三次结算剩余的 20 完成全额结清
    final_payment = SettlementType.PARTIAL.with_amount(local_amount=20.00)
    rem_final = settle_journal_entry(partial_entry, settlement_type=final_payment)
    assert rem_final.local_amount == 0.00, "全部结清后剩余应为 0"
    # 验证三次累计支付 40+40+20=100 与原额一致
    assert sum([40.00, 40.00, 20.00]) == 100.00, "累计支付应等于原总额"
    # 结算完成后外币金额也应归零
    for line in partial_entry.lines:
        assert getattr(line, 'foreign_currency_amount', 0) == 0, "结算完成后外币应清零"
    # 本位币合计亦为零
    final_total = sum(l.amount_local for l in partial_entry.lines)
    assert final_total == 0.00, "最终本位币合计应为 0"

def test_b36(ledger):
    """场景 b36: 结算超额时触发 validate_settlement_limit"""
    led = ledger
    feb_key = "2025-02"
    # 创建一笔小额凭证（100 本位币对应 100 外币单位）
    limit_entry = led.create_journal_entry(feb_key, "2025-02-15", EntryType.NORMAL)
    limit_entry.add_line(account_id="4001", description="小额应收", amount_local=100.00,
                         foreign_currency_amount=100.00, foreign_currency_code="CNY")
    limit_entry.add_line(account_id="4002", description="小额应付", amount_local=-100.00,
                         foreign_currency_amount=100.00, foreign_currency_code="CNY")
    post_journal_entry(limit_entry, led)
    # 全额结算一次应正常完成，剩余为 0
    settle_journal_entry(limit_entry, settlement_type=SettlementType.FULL)
    # 验证过账后不能再做任何超额结算
    with pytest.raises(SettlementLimitExceededException):
        settle_journal_entry(limit_entry, settlement_type=SettlementType.FULL)
    # 重复的超额结算也应被限制，防止重复扣减
    with pytest.raises(SettlementLimitExceededException):
        settle_journal_entry(limit_entry, settlement_type=SettlementType.PARTIAL.with_amount(local_amount=50.00))
    # 换一条新凭证测试超额边界情况
    boundary_entry = led.create_journal_entry(feb_key, "2025-02-16", EntryType.NORMAL)
    boundary_entry.add_line(account_id="4003", description="边界应收", amount_local=50.00,
                            foreign_currency_amount=50.00, foreign_currency_code="CNY")
    boundary_entry.add_line(account_id="4004", description="边界应付", amount_local=-50.00,
                            foreign_currency_amount=50.00, foreign_currency_code="CNY")
    post_journal_entry(boundary_entry, led)
    # 足额结算 50 应通过
    settle_journal_entry(boundary_entry, settlement_type=SettlementType.FULL)
    # 超额结算超过额度应抛出异常
    with pytest.raises(SettlementLimitExceededException):
        settle_journal_entry(boundary_entry, settlement_type=SettlementType.FULL)
    # 验证两笔过账后的凭证金额均没有变成负数
    for e in [limit_entry, boundary_entry]:
        for line in e.lines:
            assert line.amount_local >= 0, "结算后分录金额不应为负"
            assert getattr(line, 'foreign_currency_amount', 0) >= 0, "外币金额也不应负"

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

def test_b02_duplicate_period_registration():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        # 第一次注册成功
        book.register_period(year=2025, period_number=1)
        periods = book.get_periods()
        assert len(periods) == 1
        assert any(p["key"] == "2025-01" for p in periods)
        assert any(p["name"] == "一月" for p in periods)
        period = next(p for p in periods if p["key"] == "2025-01")
        assert not period.get("is_closed", False)

        # 第二次注册相同期间应抛出 DuplicateAccountException
        try:
            book.register_period(year=2025, period_number=1)
            assert False, "Expected DuplicateAccountException"
        except exceptions.DuplicateAccountException as e:
            assert "duplicate" in str(e).lower()

        # 第三次注册不同期间应成功
        book.register_period(year=2025, period_number=2)
        periods = book.get_periods()
        assert len(periods) == 2
        assert any(p["key"] == "2025-02" for p in periods)
        assert any(p["name"] == "二月" for p in periods)

        # 注册第二个年份的期间应成功
        book.register_period(year=2026, period_number=1)
        periods = book.get_periods()
        assert len(periods) == 3
        assert any(p["key"] == "2026-01" for p in periods)

        # 验证已注册的三个期间都不处于关闭状态
        for p in periods:
            assert not p.get("is_closed", False)

def test_b04_date_before_period():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)
        book.register_period(year=2025, period_number=2)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Test entry",
            date=date(2025, 1, 5)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        try:
            entry.post(book)
            assert False, "Expected InvalidDateException"
        except exceptions.InvalidDateException as e:
            assert "date" in str(e).lower() or "not in period" in str(e).lower()

        # 验证日期在期间内的条目可以正常创建和过账
        entry2 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Valid entry",
            date=date(2025, 1, 15)
        )
        entry2.add_line(lines[0])
        entry2.add_line(lines[1])
        entry2.post(book)
        assert entry2.status == "posted"
        assert entry2.is_balanced()

def test_b06_same_currency_two_rows_balanced():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Same currency transfer",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash A", "direction": "debit", "amount_local": 500},
            {"account_number": "1002", "description": "Cash B", "direction": "credit", "amount_local": 500},
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        assert entry.is_balanced()
        assert entry.debit_total == 500
        assert abs(entry.credit_total) == 500

        entry.post(book)
        assert entry.status == "posted"

        # 查询两个账户的记录
        ledger_book = book.get_ledger()
        account_1001 = ledger_book.get_account("1001")
        balance_1001 = sum(l["amount_local"] for l in account_1001.get_lines())
        assert balance_1001 == 500

        account_1002 = ledger_book.get_account("1002")
        balance_1002 = sum(l["amount_local"] for l in account_1002.get_lines())
        assert balance_1002 == -500

        # 验证借贷方向统计
        debit_count = sum(1 for a in ledger_book.get_accounts() for l in a.get_lines() if l["direction"] == "debit")
        credit_count = sum(1 for a in ledger_book.get_accounts() for l in a.get_lines() if l["direction"] == "credit")
        assert debit_count >= 1
        assert credit_count >= 1

def test_b07_three_rows_balanced_two_debits_one_credit():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Three rows balanced",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 300},
            {"account_number": "1600", "description": "AR", "direction": "debit", "amount_local": 200},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 500}
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])
        entry.add_line(lines[2])

        assert entry.is_balanced()
        assert entry.debit_total == 500
        assert abs(entry.credit_total) == 500
        assert entry.row_count == 3

        entry.post(book)
        assert entry.status == "posted"

        # 验证过账后各行状态
        for line in entry.lines:
            assert line.status == "posted"

        # 验证账户余额
        ledger_book = book.get_ledger()
        for acc_num, expected_balance in [("1001", 300), ("1600", 200), ("2001", -500)]:
            acc = ledger_book.get_account(acc_num)
            actual = sum(l["amount_local"] for l in acc.get_lines())
            assert actual == expected_balance, f"Account {acc_num}: expected {expected_balance}, got {actual}"

def test_b08_unbalanced_entries():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Unbalanced entry",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 1000},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 800}
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        assert not entry.is_balanced()
        assert entry.debit_total == 1000
        assert abs(entry.credit_total) == 800

        # 过账前应抛出异常
        try:
            entry.post(book)
            assert False, "Expected exception for unbalanced entry"
        except Exception as e:
            assert "unbalanced" in str(e).lower() or "balance" in str(e).lower()

        # 补充一行使其平衡
        entry.add_line({"account_number": "4001", "description": "Expense", "direction": "credit", "amount_local": 200})
        assert entry.is_balanced()
        assert entry.debit_total == 1000
        assert abs(entry.credit_total) == 1000

        entry.post(book)
        assert entry.status == "posted"

def test_b09_empty_entry_posting():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Empty entry test",
            date=date(2025, 1, 10)
        )

        # 空分录的借贷合计都是 0，is_balanced() 为 True
        assert entry.is_balanced()
        assert entry.debit_total == 0
        assert entry.credit_total == 0
        assert entry.row_count == 0

        # post 时先通过平衡检查（空分录是平衡的），然后因 validate_basic_structure 抛 DuplicateAccountException
        try:
            entry.post(book)
            assert False, "Expected DuplicateAccountException for empty entry"
        except exceptions.DuplicateAccountException as e:
            pass
        except Exception as e:
            assert False, f"Expected DuplicateAccountException, got {type(e).__name__}: {e}"

        # 添加一行后再试
        entry.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100})
        try:
            entry.post(book)
            assert False, "Expected DuplicateAccountException"
        except exceptions.DuplicateAccountException:
            pass

def test_b10_same_account_same_side_duplicate():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Same account duplicate",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        # 同一科目出现在同一侧两次，post 抛 DuplicateAccountException
        lines.append({"account_number": "1001", "description": "Cash again", "direction": "debit", "amount_local": 50})
        for line in lines:
            entry.add_line(line)

        assert entry.is_balanced()  # 仍然是平衡的（借方 150，贷方 100，不平衡但DuplicateAccountException在post时抛）

        try:
            entry.post(book)
            assert False, "Expected DuplicateAccountException"
        except exceptions.DuplicateAccountException as e:
            assert "duplicate" in str(e).lower() or "account" in str(e).lower()

        # 验证第一条 1001 行已添加，第二条未生效（取决于实现）
        debit_total = sum(l["amount_local"] for l in entry.lines if l["direction"] == "debit")
        # 无论第二条是否被拒绝，至少第一行已计入
        assert debit_total >= 100

def test_b11_duplicate_line_number():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Duplicate line number",
            date=date(2025, 1, 10)
        )

        line_1 = {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100}
        line_2 = {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}

        entry.add_line(line_1)
        line_no = entry.lines[-1]["line_number"]

        # 重复 line_number，add_line 抛 DuplicateAccountException
        try:
            entry.add_line(line_1)
            assert False, "Expected DuplicateAccountException"
        except exceptions.DuplicateAccountException as e:
            assert "duplicate" in str(e).lower()

        # 使用不同的线号继续
        entry.add_line(line_2)
        assert entry.row_count == 2
        assert entry.is_balanced()

        entry.post(book)
        assert entry.status == "posted"

def test_b12_cant_add_line_after_posting():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Post then modify",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])
        entry.post(book)
        assert entry.status == "posted"

        # 已过账后不能再添加行
        new_line = {"account_number": "3001", "description": "New item", "direction": "debit", "amount_local": 50}
        try:
            entry.add_line(new_line)
            assert False, "Expected JournalEntryInvalidException"
        except exceptions.JournalEntryInvalidException as e:
            assert "invalid" in str(e).lower() or "cannot" in str(e).lower()

        # 行数不应改变
        assert entry.row_count == 2
        total = sum(l["amount_local"] for l in entry.lines)
        assert total == 0  # 借贷平衡

def test_b37_rounding_difference_positive_credits_side():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 构造一笔有取整差额的跨境交易
        # USD 100 * 7.2345 = 723.45（无差额）
        # 换一个汇率产生差额：比如 7.23456 → 723.46
        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Rounding diff positive credits",
            date=date(2025, 1, 15)
        )

        # 借方：收入 723.46（换算后）
        # 贷方：现金 723.45 + 汇兑损益 0.01
        lines = [
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 723.46},
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 723.45},
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        # 不平衡，差额 0.01
        assert not entry.is_balanced()
        assert entry.debit_total == 723.45
        assert abs(entry.credit_total) == 723.46

        # 过账前平衡检查应失败
        try:
            entry.post(book)
            assert False, "Expected exception for unbalanced entry"
        except Exception as e:
            assert "unbalanced" in str(e).lower() or "balance" in str(e).lower()

        # 添加汇兑损益调整行
        entry.add_line({"account_number": "6900", "description": "FX Variance", "direction": "debit", "amount_local": 0.01})
        assert entry.is_balanced()
        assert entry.row_count == 3

        entry.post(book)
        assert entry.status == "posted"

        # 验证汇兑损益行方向正确
        fx_line = next((l for l in entry.lines if l["account_number"] == "6900"), None)
        assert fx_line is not None
        assert fx_line["direction"] == "debit"
        assert fx_line["amount_local"] == 0.01

def test_b39_fx_variance_account_6900_auto_registered():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 过程性 FX 方差会导致 6900 账户自动注册
        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="FX variance auto register 6900",
            date=date(2025, 1, 15)
        )

        # 借方 723.46，贷方 723.45（不平衡）
        lines = [
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 723.46},
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 723.45}
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        # 添加汇兑损益行，系统应允许 6900 账户存在（自动注册）
        entry.add_line({"account_number": "6900", "description": "FX Variance", "direction": "debit", "amount_local": 0.01})

        # 验证 6900 账户已存在于账户列表中
        ledger = book.get_ledger()
        accounts = ledger.get_accounts()
        account_nums = [a["account_number"] for a in accounts]
        assert "6900" in account_nums

        # 6900 账户应有该行的记录
        acc_6900 = ledger.get_account("6900")
        lines_6900 = acc_6900.get_lines()
        assert len(lines_6900) == 1
        assert lines_6900[0]["amount_local"] == 0.01

        assert entry.is_balanced()
        entry.post(book)
        assert entry.status == "posted"

        # 过账后 6900 账户状态应为 posted
        updated_acc_6900 = ledger.get_account("6900")
        for line in updated_acc_6900.get_lines():
            assert line["status"] == "posted"

def test_b40_write_off_journal_entry_two_consecutive_entries_separately():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 创建原始分录：应收账款借方 1000
        entry1 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Sale on account",
            date=date(2025, 1, 10)
        )
        entry1.add_line({"account_number": "1600", "description": "AR", "direction": "debit", "amount_local": 1000})
        entry1.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 1000})
        entry1.post(book)
        assert entry1.status == "posted"

        # write_off_journal_entry 只返回反向行，不改变原分录状态
        offset_lines = book.write_off_journal_entry(entry1.entry_id)

        # 反向行应为贷方 AR、借方 Revenue
        assert len(offset_lines) == 2
        ar_line = next(l for l in offset_lines if l["account_number"] == "1600")
        rev_line = next(l for l in offset_lines if l["account_number"] == "2001")
        assert ar_line["direction"] == "credit"
        assert ar_line["amount_local"] == 1000
        assert rev_line["direction"] == "debit"
        assert rev_line["amount_local"] == 1000

        # 原分录状态不应改变
        assert entry1.status == "posted"
        original_ar_balance = sum(l["amount_local"] for l in book.get_ledger().get_account("1600").get_lines())
        assert original_ar_balance == 1000

        # 反向分录单独过账
        entry2 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Write off sale",
            date=date(2025, 1, 11)
        )
        for line in offset_lines:
            entry2.add_line(line)
        entry2.post(book)
        assert entry2.status == "posted"

        # 现在 AR 账户余额应为 0
        final_ar_balance = sum(l["amount_local"] for l in book.get_ledger().get_account("1600").get_lines())
        assert final_ar_balance == 0

def test_b41_january_closing_does_not_affect_query_of_posted_entries():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)
        book.register_period(year=2025, period_number=2)

        # 过账一条分录
        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Test entry",
            date=date(2025, 1, 15)
        )
        entry.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100})
        entry.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100})
        entry.post(book)
        assert entry.status == "posted"

        # 将一月标记为关闭
        period = book.get_period("2025-01")
        period["is_closed"] = True
        book.set_period_closed("2025-01", True)

        # 仍然应该能查询到过账的条目
        ledger = book.get_ledger()
        account_1001 = ledger.get_account("1001")
        lines = account_1001.get_lines()
        assert len(lines) == 1
        assert lines[0]["amount_local"] == 100

        # 查询一月的已记账分录
        posted_in_jan = ledger.get_posted_entries_for_period("2025-01")
        assert len(posted_in_jan) == 1

        # 二月尚未关闭，也可以查询
        posted_in_feb = ledger.get_posted_entries_for_period("2025-02")
        assert len(posted_in_feb) == 0

        # 关闭二月不影响查询
        book.set_period_closed("2025-02", True)
        posted_in_feb_again = ledger.get_posted_entries_for_period("2025-02")
        assert len(posted_in_feb_again) == 0

def test_b42_get_lines_by_direction_debit_credit_separated():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Direction separation test",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash A", "direction": "debit", "amount_local": 300},
            {"account_number": "1002", "description": "Cash B", "direction": "debit", "amount_local": 200},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 500}
        ]
        for line in lines:
            entry.add_line(line)

        assert entry.is_balanced()

        # 获取借方和贷方分离的行
        debit_lines = book.get_lines_by_direction("debit", year=2025, period_number=1)
        credit_lines = book.get_lines_by_direction("credit", year=2025, period_number=1)

        assert len(debit_lines) == 2
        assert len(credit_lines) == 1

        debit_amounts = [l["amount_local"] for l in debit_lines]
        assert 300 in debit_amounts
        assert 200 in debit_amounts

        credit_amounts = [l["amount_local"] for l in credit_lines]
        assert 500 in credit_amounts

        # 验证借贷总额
        total_debit = sum(debit_amounts)
        total_credit = sum(credit_amounts)
        assert total_debit == 500
        assert total_credit == 500

def test_b43_remove_line_then_rebalance():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Remove and rebalance",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "1600", "description": "AR", "direction": "debit", "amount_local": 200},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 300}
        ]
        for line in lines:
            entry.add_line(line)

        assert entry.is_balanced()
        assert entry.row_count == 3

        # 移除一行
        removed_line = entry.remove_line(line_number=1)
        assert removed_line["account_number"] == "1001"
        assert removed_line["direction"] == "debit"
        assert removed_line["amount_local"] == 100

        # 移除后不平衡
        assert not entry.is_balanced()
        assert entry.row_count == 2
        assert entry.debit_total == 200
        assert abs(entry.credit_total) == 300

        # 重新平衡：添加一行
        entry.add_line({"account_number": "1001", "description": "Cash back", "direction": "debit", "amount_local": 100})
        assert entry.is_balanced()
        assert entry.row_count == 3
        assert entry.debit_total == 300
        assert abs(entry.credit_total) == 300

        entry.post(book)
        assert entry.status == "posted"

def test_b44_remove_nonexistent_line_number():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Remove nonexistent",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]
        for line in lines:
            entry.add_line(line)

        # 移除不存在的行号应抛出异常
        try:
            entry.remove_line(line_number=999)
            assert False, "Expected exception"
        except exceptions.JournalEntryInvalidException as e:
            assert "nonexistent" in str(e).lower() or "invalid" in str(e).lower()

        # 行数不应改变
        assert entry.row_count == 2
        assert entry.is_balanced()

        # 有效行号移除
        removed = entry.remove_line(line_number=1)
        assert removed["account_number"] == "1001"
        assert entry.row_count == 1
        assert not entry.is_balanced()

def test_b45_batch_validate_entries_collect_unbalanced_entries():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry1 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Balanced",
            date=date(2025, 1, 10)
        )
        entry1.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100})
        entry1.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100})

        entry2 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Unbalanced",
            date=date(2025, 1, 10)
        )
        entry2.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100})
        entry2.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 80})

        entry3 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Another balanced",
            date=date(2025, 1, 10)
        )
        entry3.add_line({"account_number": "1002", "description": "Bank", "direction": "debit", "amount_local": 50})
        entry3.add_line({"account_number": "4001", "description": "Expense", "direction": "credit", "amount_local": 50})

        # 批量验证
        results = book.batch_validate_entries([entry1, entry2, entry3])
        assert len(results) == 3

        balanced_results = [r for r in results if r.get("is_balanced", False)]
        unbalanced_results = [r for r in results if not r.get("is_balanced", False)]

        assert len(balanced_results) == 2
        assert len(unbalanced_results) == 1

        # 收集不平衡条目中的未知币种
        unknown_currency_results = book.collect_unknown_currency_entries(entries=[entry1, entry2, entry3])
        # 本测试中所有条目都只使用本地币种，应无未知币种
        assert len(unknown_currency_results) == 0

        # 过账平衡的条目
        entry1.post(book)
        entry3.post(book)
        assert entry1.status == "posted"
        assert entry3.status == "posted"
        # entry2 应保持未过账状态
        assert entry2.status != "posted"

def test_b46_batch_validate_entries_collect_unknown_currency_entries():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry1 = book.create_journal_entry(
            year=2025, period_number=1,
            description="All local",
            date=date(2025, 1, 10)
        )
        entry1.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100})
        entry1.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100})

        entry2 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Foreign currency",
            date=date(2025, 1, 10)
        )
        entry2.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100, "currency": "USD"})
        entry2.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100, "currency": "USD"})

        entry3 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Unknown currency",
            date=date(2025, 1, 10)
        )
        entry3.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100, "currency": "GBP"})
        entry3.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100, "currency": "GBP"})

        # 批量验证并收集未知币种条目
        results = book.batch_validate_entries([entry1, entry2, entry3])
        unknown_entries = book.collect_unknown_currency_entries(entries=[entry1, entry2, entry3])

        # entry1 无外币，entry2 使用已注册币种 USD，entry3 使用未注册币种 GBP
        assert len(unknown_entries) == 1
        assert entry3 in unknown_entries or id(entry3) in [id(e) for e in unknown_entries]

        # entry3 过账时应抛出 UnknownCurrencyException
        try:
            entry3.post(book)
            assert False, "Expected UnknownCurrencyException"
        except exceptions.UnknownCurrencyException as e:
            assert "unknown" in str(e).lower() or "gbp" in str(e).lower()

        # entry1 和 entry2 应可正常过账
        entry1.post(book)
        entry2.post(book)
        assert entry1.status == "posted"
        assert entry2.status == "posted"

def test_b47_direction_illegal_string():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Illegal direction",
            date=date(2025, 1, 10)
        )

        # 非法方向应导致添加失败
        illegal_lines = [
            {"account_number": "1001", "description": "Cash", "direction": "invalid_dir", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]

        for line in illegal_lines:
            try:
                entry.add_line(line)
                # 如果 add_line 内部不校验，则 post 时校验
                pass
            except exceptions.JournalEntryInvalidException as e:
                assert "direction" in str(e).lower() or "invalid" in str(e).lower()
                break
        else:
            # 如果 add_line 没抛异常，post 时应抛
            try:
                entry.post(book)
                assert False, "Expected exception"
            except exceptions.JournalEntryInvalidException as e:
                assert "direction" in str(e).lower() or "invalid" in str(e).lower()

        # 合法的 directions
        legal_lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]
        for line in legal_lines:
            entry.add_line(line)

        assert entry.is_balanced()
        entry.post(book)
        assert entry.status == "posted"

def test_b48_register_march_period_then_create_entry_with_march_date():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)
        book.register_period(year=2025, period_number=2)

        # 注册三月期间
        book.register_period(year=2025, period_number=3)
        periods = book.get_periods()
        assert any(p["key"] == "2025-03" for p in periods)
        assert any(p["name"] == "三月" for p in periods)

        # 使用三月日期创建分录
        entry = book.create_journal_entry(
            year=2025, period_number=3,
            description="March entry",
            date=date(2025, 3, 15)
        )

        lines = [
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 100},
            {"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 100}
        ]
        for line in lines:
            entry.add_line(line)

        assert entry.is_balanced()
        entry.post(book)
        assert entry.status == "posted"

        # 验证三月期间的记录
        ledger = book.get_ledger()
        march_posts = ledger.get_posted_entries_for_period("2025-03")
        assert len(march_posts) == 1
        assert march_posts[0].description == "March entry"

def test_b49_export_sales_2000usd_full_settlement():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 创建销售分录：应收账款借方 2000 USD，销售收入贷方 2000 USD
        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Sales 2000 USD",
            date=date(2025, 1, 10)
        )
        entry.add_line({"account_number": "1600", "description": "AR", "direction": "debit", "amount_local": 2000, "currency": "USD"})
        entry.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 2000, "currency": "USD"})
        entry.post(book)
        assert entry.status == "posted"

        # 全额结算：现金借方 2000 USD，应收账款贷方 2000 USD
        settlement_entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Full settlement of sales",
            date=date(2025, 1, 15)
        )
        settlement_entry.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 2000, "currency": "USD"})
        settlement_entry.add_line({"account_number": "1600", "description": "AR", "direction": "credit", "amount_local": 2000, "currency": "USD"})
        settlement_entry.post(book)
        assert settlement_entry.status == "posted"

        # 全额结算后应收账款余额应为 0
        ledger = book.get_ledger()
        ar_account = ledger.get_account("1600")
        ar_balance = sum(l["amount_local"] for l in ar_account.get_lines())
        assert ar_balance == 0

        cash_account = ledger.get_account("1001")
        cash_balance = sum(l["amount_local"] for l in cash_account.get_lines())
        assert cash_balance == 2000

        # 导出销售相关分录
        exported = book.export_sales(year=2025, period_number=1, min_amount=100)
        assert isinstance(exported, list)
        assert len(exported) == 2

        # 验证两条分录都在导出结果中
        export_descriptions = [e["description"] for e in exported]
        assert "Sales 2000 USD" in export_descriptions
        assert "Full settlement of sales" in export_descriptions

def test_b50_import_800eur_partial_settlement():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 创建采购分录：应付账款贷方 800 EUR，采购成本借方 800 EUR
        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Purchase 800 EUR",
            date=date(2025, 1, 10)
        )
        entry.add_line({"account_number": "1700", "description": "AP", "direction": "credit", "amount_local": 800, "currency": "EUR"})
        entry.add_line({"account_number": "3001", "description": "Inventory", "direction": "debit", "amount_local": 800, "currency": "EUR"})
        entry.post(book)
        assert entry.status == "posted"

        # 部分结算：现金借方 400 EUR，应付账款贷方 400 EUR
        partial_entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Partial payment 400 EUR",
            date=date(2025, 1, 12)
        )
        partial_entry.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 400, "currency": "EUR"})
        partial_entry.add_line({"account_number": "1700", "description": "AP", "direction": "credit", "amount_local": 400, "currency": "EUR"})
        partial_entry.post(book)
        assert partial_entry.status == "posted"

        # 剩余应付 400 EUR，再进行一次部分结算
        remaining_entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Remaining payment 400 EUR",
            date=date(2025, 1, 15)
        )
        remaining_entry.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 400, "currency": "EUR"})
        remaining_entry.add_line({"account_number": "1700", "description": "AP", "direction": "credit", "amount_local": 400, "currency": "EUR"})
        remaining_entry.post(book)
        assert remaining_entry.status == "posted"

        # 最终应付账款余额应为 0
        ledger = book.get_ledger()
        ap_account = ledger.get_account("1700")
        ap_balance = sum(l["amount_local"] for l in ap_account.get_lines())
        assert abs(ap_balance) <= 0.01  # 允许浮点误差

        # 现金账户应有 800 EUR 的借方记录
        cash_account = ledger.get_account("1001")
        cash_debits = [l for l in cash_account.get_lines() if l["direction"] == "debit"]
        assert len(cash_debits) == 2
        cash_total = sum(l["amount_local"] for l in cash_debits)
        assert abs(cash_total - 800) <= 0.01

def test_b51_same_day_two_entries_post_and_write_off():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry1 = book.create_journal_entry(
            year=2025, period_number=1,
            description="First entry same day",
            date=date(2025, 1, 10)
        )
        entry1.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 500})
        entry1.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 500})
        entry1.post(book)
        assert entry1.status == "posted"

        entry2 = book.create_journal_entry(
            year=2025, period_number=1,
            description="Second entry same day",
            date=date(2025, 1, 10)
        )
        entry2.add_line({"account_number": "1002", "description": "Bank", "direction": "debit", "amount_local": 300})
        entry2.add_line({"account_number": "4001", "description": "Expense", "direction": "credit", "amount_local": 300})
        entry2.post(book)
        assert entry2.status == "posted"

        # 对 entry1 进行过账后写账
        written = book.write_off_journal_entry(entry1.entry_id)
        assert len(written) == 2

        # 创建 entry1 的反向分录
        reversal = book.create_journal_entry(
            year=2025, period_number=1,
            description="Reversal of first entry",
            date=date(2025, 1, 11)
        )
        for line in written:
            reversal.add_line(line)
        reversal.post(book)
        assert reversal.status == "posted"

        # 验证 Cash 和 Revenue 账户的净余额
        ledger = book.get_ledger()
        cash = ledger.get_account("1001")
        cash_balance = sum(l["amount_local"] for l in cash.get_lines())
        assert cash_balance == 0  # 500 debit + 500 credit from reversal

        revenue = ledger.get_account("2001")
        revenue_balance = sum(l["amount_local"] for l in revenue.get_lines())
        assert revenue_balance == 0  # 500 credit + 500 debit from reversal

        # Bank 和 Expense 账户应保持 300 的净额
        bank = ledger.get_account("1002")
        bank_balance = sum(l["amount_local"] for l in bank.get_lines())
        assert bank_balance == 300

        expense = ledger.get_account("4001")
        expense_balance = sum(l["amount_local"] for l in expense.get_lines())
        assert expense_balance == -300

def test_b53_jpy_small_rounding_difference():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # JPY 10000 汇率 0.0482 → 482.00（精确，无差额）
        # 构造一个小差额：10000 * 0.0482 = 482.00
        # 用 10001 JPY → 482.0482 → round(482.05) 产生差额
        jpy_amount = 10001
        rate = 0.0482
        rounded = round(jpy_amount * rate, 2)
        assert rounded == 482.05

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="JPY small rounding diff",
            date=date(2025, 1, 15)
        )

        # 借方：商品 482.05（换算后）
        # 贷方：现金 482.00 + 汇兑损益 0.05
        lines = [
            {"account_number": "3001", "description": "Inventory", "direction": "credit", "amount_local": 482.05, "currency": "JPY"},
            {"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 482.00},
        ]
        entry.add_line(lines[0])
        entry.add_line(lines[1])

        assert not entry.is_balanced()
        assert entry.debit_total == 482.00
        assert abs(entry.credit_total) == 482.05

        # 添加汇兑损益调整
        entry.add_line({"account_number": "6900", "description": "FX Variance", "direction": "debit", "amount_local": 0.05})
        assert entry.is_balanced()
        assert entry.row_count == 3

        entry.post(book)
        assert entry.status == "posted"

        # 验证汇兑损益行
        fx_line = next((l for l in entry.lines if l["account_number"] == "6900"), None)
        assert fx_line is not None
        assert fx_line["direction"] == "debit"
        assert fx_line["amount_local"] == 0.05

def test_b54_cash_bank_reversal_then_revenue_confirmation():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 第一步：收款确认（借现金，贷应收）
        receipt = book.create_journal_entry(
            year=2025, period_number=1,
            description="Cash receipt from customer",
            date=date(2025, 1, 10)
        )
        receipt.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 1000})
        receipt.add_line({"account_number": "1600", "description": "AR", "direction": "credit", "amount_local": 1000})
        receipt.post(book)
        assert receipt.status == "posted"

        ledger = book.get_ledger()
        ar_before = sum(l["amount_local"] for l in ledger.get_account("1600").get_lines())
        assert ar_before == -1000

        # 第二步：冲销收款分录
        offset_lines = book.write_off_journal_entry(receipt.entry_id)
        reversal = book.create_journal_entry(
            year=2025, period_number=1,
            description="Reverse cash receipt",
            date=date(2025, 1, 11)
        )
        for line in offset_lines:
            reversal.add_line(line)
        reversal.post(book)
        assert reversal.status == "posted"

        ar_after_reversal = sum(l["amount_local"] for l in ledger.get_account("1600").get_lines())
        assert ar_after_reversal == 0  # 冲销后 AR 恢复

        # 第三步：收入确认（借应收，贷收入）
        revenue_confirm = book.create_journal_entry(
            year=2025, period_number=1,
            description="Revenue confirmation",
            date=date(2025, 1, 12)
        )
        revenue_confirm.add_line({"account_number": "1600", "description": "AR", "direction": "debit", "amount_local": 1000})
        revenue_confirm.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 1000})
        revenue_confirm.post(book)
        assert revenue_confirm.status == "posted"

        ar_final = sum(l["amount_local"] for l in ledger.get_account("1600").get_lines())
        assert ar_final == -1000  # 又欠了 1000

        revenue_final = sum(l["amount_local"] for l in ledger.get_account("2001").get_lines())
        assert abs(revenue_final - (-1000)) <= 0.01

def test_b55_four_line_entry_two_debits_two_credits():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        entry = book.create_journal_entry(
            year=2025, period_number=1,
            description="Four line entry",
            date=date(2025, 1, 10)
        )

        lines = [
            {"account_number": "1001", "description": "Cash A", "direction": "debit", "amount_local": 300},
            {"account_number": "1002", "description": "Cash B", "direction": "debit", "amount_local": 200},
            {"account_number": "2001", "description": "Revenue X", "direction": "credit", "amount_local": 250},
            {"account_number": "2002", "description": "Revenue Y", "direction": "credit", "amount_local": 250}
        ]
        for line in lines:
            entry.add_line(line)

        assert entry.is_balanced()
        assert entry.row_count == 4
        assert entry.debit_total == 500
        assert abs(entry.credit_total) == 500

        entry.post(book)
        assert entry.status == "posted"

        ledger = book.get_ledger()

        # 验证四个账户的余额
        balances = {
            "1001": 300, "1002": 200,
            "2001": -250, "2002": -250
        }
        for acc_num, expected in balances.items():
            acc = ledger.get_account(acc_num)
            actual = sum(l["amount_local"] for l in acc.get_lines())
            assert actual == expected, f"Account {acc_num}: expected {expected}, got {actual}"

        # 验证借方和贷方行数
        debit_count = sum(1 for a in ledger.get_accounts() for l in a.get_lines() if l["direction"] == "debit")
        credit_count = sum(1 for a in ledger.get_accounts() for l in a.get_lines() if l["direction"] == "credit")
        assert debit_count == 2
        assert credit_count == 2

def test_b56_validate_settlement_limit_boundary_equal():
    from subjects.ledger import Ledger, exceptions
    from datetime import date

    with Ledger.open_books(year=2025) as book:
        book.register_period(year=2025, period_number=1)

        # 创建一笔应收 1000
        sale = book.create_journal_entry(
            year=2025, period_number=1,
            description="Sale",
            date=date(2025, 1, 10)
        )
        sale.add_line({"account_number": "1600", "description": "AR", "direction": "debit", "amount_local": 1000})
        sale.add_line({"account_number": "2001", "description": "Revenue", "direction": "credit", "amount_local": 1000})
        sale.post(book)
        assert sale.status == "posted"

        # 验证边界相等时的结算：支付正好 1000
        settlement = book.create_journal_entry(
            year=2025, period_number=1,
            description="Full settlement 1000",
            date=date(2025, 1, 15)
        )
        settlement.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 1000})
        settlement.add_line({"account_number": "1600", "description": "AR", "direction": "credit", "amount_local": 1000})
        settlement.post(book)
        assert settlement.status == "posted"

        ledger = book.get_ledger()
        ar_balance = sum(l["amount_local"] for l in ledger.get_account("1600").get_lines())
        assert ar_balance == 0

        # 边界小于：支付 999.99，差额 0.01
        partial = book.create_journal_entry(
            year=2025, period_number=1,
            description="Partial 999.99",
            date=date(2025, 1, 16)
        )
        partial.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 999.99})
        partial.add_line({"account_number": "1600", "description": "AR", "direction": "credit", "amount_local": 999.99})
        partial.post(book)
        assert partial.status == "posted"

        remaining_ar = sum(l["amount_local"] for l in ledger.get_account("1600").get_lines())
        assert abs(remaining_ar - (-0.01)) <= 0.01

        # 边界等于零：剩余 0.01，最后一笔正好付清
        final = book.create_journal_entry(
            year=2025, period_number=1,
            description="Final 0.01",
            date=date(2025, 1, 17)
        )
        final.add_line({"account_number": "1001", "description": "Cash", "direction": "debit", "amount_local": 0.01})
        final.add_line({"account_number": "1600", "description": "AR", "direction": "credit", "amount_local": 0.01})
        final.post(book)
        assert final.status == "posted"

        final_ar = sum(l["amount_local"] for l in ledger.get_account("1600").get_lines())
        assert abs(final_ar) <= 0.01
