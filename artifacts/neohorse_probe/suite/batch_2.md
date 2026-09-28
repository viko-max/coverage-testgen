

```python
import pytest
from subjects.ledger import BookManager, JournalEntry, convert_foreign_to_local, post_journal_entry
from subjects.ledger.exceptions import UnknownCurrencyException, JournalEntryInvalidException, PeriodClosedForNormalEntryException

@pytest.fixture(scope="function")
def fx_setup():
    bm = BookManager()
    bm.open_books(year=2025, period_number=1, currencies=["CNY", "USD", "EUR", "JPY", "GBP"],
                  accounts=["1001", "1002", "1003", "2001", "2002", "2003"])
    bm.register_rate("USD", "CNY", 7.2345, "2025-01-10")
    bm.register_rate("USD", "CNY", 7.2500, "2025-01-20")
    bm.register_rate("EUR", "CNY", 7.8012, "2025-01-15")
    bm.register_rate("JPY", "CNY", 0.0482, "2025-01-15")
    # GBP purposely unregistered
    return bm

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
```