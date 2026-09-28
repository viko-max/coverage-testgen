

```python
import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

getcontext().prec = 28


# ============================================================
# 异常定义
# ============================================================

class AccountingError(Exception):
    """会计系统基础异常"""
    pass


class JournalEntryInvalidException(AccountingError):
    """借贷不平异常：分录借方合计与贷方合计不相等"""
    def __init__(self, message: str, debit: Decimal = None, credit: Decimal = None):
        super().__init__(message)
        self.debit = debit
        self.credit = credit


class PeriodClosedForNormalEntryException(AccountingError):
    """关账后普通入账异常：已关闭的会计期间不允许进行普通业务分录"""
    pass


class UnknownCurrencyException(AccountingError):
    """未知币种异常：系统中不存在该货币代码"""
    pass


class ExchangeRateMissingException(AccountingError):
    """汇率缺失异常：找不到指定日期或任何可用日期的汇率"""
    pass


class SettlementOverdueException(AccountingError):
    """结算超额异常：本次结算金额超过待结算总额"""
    pass


class InsufficientFundsException(AccountingError):
    """余额不足异常：账户可用余额不足以完成结算"""
    pass


class DuplicateAccountException(AccountingError):
    """重复账户异常：同一账户在同一分录借/贷方内重复出现"""
    pass


class InvalidDateException(AccountingError):
    """无效日期异常：日期不在有效范围内"""
    pass


class NegativeAmountException(AccountingError):
    """负数金额异常：单笔分录的绝对金额不能为负数"""
    pass


class EmptyJournalEntryException(AccountingError):
    """空分录异常：分录中必须至少包含一行"""
    pass


class UnsupportedCurrencyException(AccountingError):
    """不支持的币种异常：该币种不在系统支持的范围内"""
    pass


class UnsupportedAdjustmentTypeException(AccountingError):
    """不支持的调整类型异常"""
    pass


# ============================================================
# 枚举定义
# ============================================================

class AccountType(Enum):
    ASSET = "资产"
    LIABILITY = "负债"
    EQUITY = "所有者权益"
    REVENUE = "收入"
    EXPENSE = "费用"
    INCOME_TAX = "所得税"
    OTHER = "其他"


class EntryStatus(Enum):
    DRAFT = "草稿"
    POSTED = "已过账"
    CANCELLED = "已冲销"
    CLOSED = "已关闭"


class SettlementType(Enum):
    FULL = "全额结算"
    PARTIAL = "部分结算"


class AdjustmentType(Enum):
    CORRECTION = "更正"
    ADJUSTMENT = "调整"
    WRITE_OFF = "核销"
    FX_GAIN = "汇兑收益"
    FX_LOSS = "汇兑损失"


# ============================================================
# 数据类
# ============================================================

@dataclass
class Currency:
    code: str
    name: str
    symbol: str = ""
    decimal_places: int = 2

    def __hash__(self):
        return hash(self.code)

    def __eq__(self, other):
        if isinstance(other, Currency):
            return self.code == other.code
        return False


@dataclass
class Account:
    account_code: str
    account_name: str
    account_type: AccountType
    currency: Currency
    balance: Decimal = Decimal("0")
    is_active: bool = True
    opening_balance_date: Optional[date] = None

    def __post_init__(self):
        if not self.account_code:
            raise ValueError("账户编号不能为空")
        if not self.account_name:
            raise ValueError("账户名称不能为空")
        if not self.currency or not self.currency.code:
            raise ValueError("币种不能为空")
        if self.balance < Decimal("0"):
            raise ValueError("初始余额不能为负数")


@dataclass
class AccountingPeriod:
    period_id: str
    period_number: int
    year: int
    start_date: date
    end_date: date
    is_closed: bool = False
    is_adjusted: bool = False
    description: str = ""
    closing_entry_date: Optional[date] = None

    @property
    def period_key(self) -> str:
        return f"{self.year}-{self.period_number:02d}"

    @property
    def is_open(self) -> bool:
        return not self.is_closed

    def contains_date(self, d: date) -> bool:
        return self.start_date <= d <= self.end_date


@dataclass
class ExchangeRate:
    quote_currency: str
    base_currency: str
    rate: Decimal
    effective_date: date
    source: str = ""


@dataclass
class ExchangeRatesTable:
    base_currency: str
    rates: Dict[str, Dict[date, Decimal]] = field(default_factory=dict)

    def get_rate(self, quote_currency: str, base_currency: str,
                 effective_date: date, precision: int = 6) -> Decimal:
        if quote_currency == base_currency:
            return Decimal("1")

        if quote_currency not in self.rates:
            raise ExchangeRateMissingException(
                f"汇率表中不存在币种 {quote_currency} 的汇率记录"
            )

        available_rates = self.rates[quote_currency]
        if not available_rates:
            raise ExchangeRateMissingException(
                f"币种 {quote_currency} 没有任何汇率数据"
            )

        exact_hit = None
        candidates = []

        for r_date, rate in available_rates.items():
            if r_date == effective_date:
                exact_hit = rate
                break
            candidates.append((r_date, rate))

        if exact_hit is not None:
            return round(exact_hit, precision)

        closest_before = max(
            (d for d, v in candidates if d <= effective_date),
            default=None,
            key=lambda x: x
        )
        if closest_before is not None:
            return round(available_rates[closest_before], precision)

        closest_after = min(
            (d for d, v in candidates if d >= effective_date),
            default=None,
            key=lambda x: x
        )
        if closest_after is not None:
            return round(available_rates[closest_after], precision)

        raise ExchangeRateMissingException(
            f"无法找到 {quote_currency} 在 {effective_date} 的汇率，"
            f"可用日期范围：{min(available_rates.keys())} ~ {max(available_rates.keys())}"
        )

    def add_rate(self, quote_currency: str, base_currency: str, rate: Decimal,
                 effective_date: date):
        if quote_currency not in self.rates:
            self.rates[quote_currency] = {}
        self.rates[quote_currency][effective_date] = round(rate, 6)


@dataclass
class JournalEntryLine:
    line_number: int
    account_code: str
    amount_local: Decimal
    amount_foreign: Decimal
    foreign_currency: str
    description: str = ""
    reference: str = ""

    @property
    def is_debit(self) -> bool:
        return self.amount_local > Decimal("0")

    @property
    def is_credit(self) -> bool:
        return self.amount_local < Decimal("0")

    @property
    def absolute_amount_local(self) -> Decimal:
        return abs(self.amount_local)

    @property
    def absolute_amount_foreign(self) -> Decimal:
        return abs(self.amount_foreign)


@dataclass
class JournalEntry:
    entry_id: str
    entry_number: str
    entry_date: date
    period_key: str
    lines: List["JournalEntryLine"] = field(default_factory=list)
    status: EntryStatus = EntryStatus.DRAFT
    description: str = ""
    created_by: str = ""
    created_at: Optional[date] = None
    posted_by: str = ""
    posted_at: Optional[date] = None

    _total_debit: Decimal = Decimal("0")
    _total_credit: Decimal = Decimal("0")

    def __post_init__(self):
        if self.lines:
            self._recalculate_totals()

    def _recalculate_totals(self):
        debit_sum = Decimal("0")
        credit_sum = Decimal("0")
        for line in self.lines:
            if line.amount_local > Decimal("0"):
                debit_sum += line.amount_local
            elif line.amount_local < Decimal("0"):
                credit_sum += abs(line.amount_local)
        self._total_debit = debit_sum
        self._total_credit = credit_sum

    @property
    def total_debit(self) -> Decimal:
        return self._total_debit

    @property
    def total_credit(self) -> Decimal:
        return self._total_credit

    def add_line(self, line: "JournalEntryLine"):
        if self.status != EntryStatus.DRAFT:
            raise JournalEntryInvalidException("只能在草稿状态下添加分录行")
        if line.line_number in [l.line_number for l in self.lines]:
            raise DuplicateAccountException("分录行序号不能重复")
        self.lines.append(line)
        self._recalculate_totals()

    def remove_line(self, line_number: int):
        for i, line in enumerate(self.lines):
            if line.line_number == line_number:
                del self.lines[i]
                self._recalculate_totals()
                return
        raise ValueError(f"未找到行号 {line_number}")

    def get_lines_by_direction(self, direction: str) -> List["JournalEntryLine"]:
        if direction.lower() == "debit":
            return [l for l in self.lines if l.amount_local > Decimal("0")]
        elif direction.lower() == "credit":
            return [l for l in self.lines if l.amount_local < Decimal("0")]
        raise ValueError("direction 必须是 'debit' 或 'credit'")

    def has_duplicate_account_per_side(self) -> bool:
        debit_accounts = {}
        credit_accounts = {}
        for line in self.lines:
            acc = line.account_code
            if line.is_debit:
                debit_accounts[acc] = debit_accounts.get(acc, 0) + 1
            else:
                credit_accounts[acc] = credit_accounts.get(acc, 0) + 1
        return any(v > 1 for v in debit_accounts.values()) or any(v > 1 for v in credit_accounts.values())

    def validate_basic_structure(self) -> bool:
        if not self.lines:
            return False
        if self.has_duplicate_account_per_side():
            return False
        return True

    def is_balanced(self) -> bool:
        diff = abs(self._total_debit - self._total_credit)
        return diff < Decimal("0.0000001")


@dataclass
class Settlement:
    settlement_id: str
    entry_id: str
    original_amount_foreign: Decimal
    original_amount_local: Decimal
    settled_amount_foreign: Decimal = Decimal("0")
    settled_amount_local: Decimal = Decimal("0")
    settlement_date: Optional[date] = None
    exchange_rate_used: Optional[Decimal] = None
    remaining_foreign: Decimal = Decimal("0")
    remaining_local: Decimal = Decimal("0")
    settlement_type: SettlementType = SettlementType.FULL
    completed: bool = False
    adjustment_lines: List[Tuple[str, Decimal]] = field(default_factory=list)

    @property
    def is_full_settled(self) -> bool:
        return abs(self.remaining_foreign) < Decimal("0.0000001")


# ============================================================
# 主管理模块：多币种复式分录结算器
# ============================================================

class MultiCurrencySettlementManager:
    """
    多币种复式分录结算器

    功能：
    1. 创建并验证会计分录（借贷必相等）
    2. 外币按汇率折算为本位币
    3. 支持红字冲销、部分结清
    4. 尾差自动进汇兑损益
    5. 关账后只允许调整分录
    6. 借贷不平、关账后普通入账、未知币种、汇率缺失、结算超额均抛相应异常
    """

    def __init__(self, base_currency: str):
        self.base_currency = base_currency
        self.accounts: Dict[str, Account] = {}
        self.periods: Dict[str, AccountingPeriod] = {}
        self.rates_table: ExchangeRatesTable = ExchangeRatesTable(base_currency=base_currency)
        self.journal_entries: Dict[str, JournalEntry] = {}
        self.settlements: Dict[str, Settlement] = {}
        self.currency_registry: Dict[str, Currency] = {}
        self._entry_counter = 0
        self._settlement_counter = 0

    # ---------- 汇率管理 ----------

    def register_currency(self, currency: Currency):
        self.currency_registry[currency.code] = currency

    def register_account(self, account: Account):
        if account.account_code in self.accounts:
            raise DuplicateAccountException(f"账户 {account.account_code} 已存在")
        self.accounts[account.account_code] = account

    def register_period(self, period: AccountingPeriod):
        if period.period_key in self.periods:
            raise DuplicateAccountException(f"会计期间 {period.period_key} 已存在")
        self.periods[period.period_key] = period

    def register_rate(self, quote_currency: str, base_currency: str, rate: Decimal,
                      effective_date: date):
        self.rates_table.add_rate(quote_currency, base_currency, rate, effective_date)

    def get_exchange_rate(self, quote_currency: str, effective_date: date) -> Decimal:
        try:
            return self.rates_table.get_rate(quote_currency, self.base_currency, effective_date)
        except ExchangeRateMissingException as e:
            raise ExchangeRateMissingException(
                f"[汇率缺失] {quote_currency} → {self.base_currency} 在 {effective_date} 无汇率：{e}"
            ) from e

    # ---------- 分录管理 ----------

    def create_journal_entry(self, entry_number: str, entry_date: date,
                             period_key: str, description: str = "") -> JournalEntry:
        period = self.periods.get(period_key)
        if not period:
            raise PeriodClosedForNormalEntryException(f"会计期间 {period_key} 不存在或未开放")
        if not period.contains_date(entry_date):
            raise InvalidDateException(f"日期 {entry_date} 不在会计期间 {period_key} 范围内")

        self._entry_counter += 1
        entry_id = f"E{self._entry_counter:06d}"
        entry = JournalEntry(
            entry_id=entry_id,
            entry_number=entry_number,
            entry_date=entry_date,
            period_key=period_key,
            description=description
        )
        self.journal_entries[entry_id] = entry
        return entry

    def adjust_journal_entry(self, entry: JournalEntry,
                              period_key: str,
                              adjustment_type: AdjustmentType):
        current_period = self.periods.get(period_key)
        if not current_period:
            raise PeriodClosedForNormalEntryException(f"会计期间 {period_key} 不存在")

        if not entry.is_balanced():
            raise JournalEntryInvalidException(
                f"调整分录借贷不平衡，借方 {entry.total_debit} ≠ 贷方 {entry.total_credit}"
            )

        # 校验是否为调整类型
        if adjustment_type not in [AdjustmentType.CORRECTION, AdjustmentType.ADJUSTMENT,
                                   AdjustmentType.WRITE_OFF, AdjustmentType.FX_GAIN, AdjustmentType.FX_LOSS]:
            raise UnsupportedAdjustmentTypeException(f"不支持的调整类型：{adjustment_type}")

        entry.status = EntryStatus.POSTED
        entry.posted_by = "system"
        entry.posted_at = date.today()
        # 这里不做额外限制，因为调整分录本身可以是未过账状态下的余额修正

    def post_journal_entry(self, entry: JournalEntry, posted_by: str = "system"):
        if not entry.is_balanced():
            raise JournalEntryInvalidException(
                f"分录借贷不平，借方 {entry.total_debit} ≠ 贷方 {entry.total_credit}"
            )
        if not entry.validate_basic_structure():
            raise DuplicateAccountException("分录中存在同一账户在借方/贷方内重复")
        if not entry.lines:
            raise EmptyJournalEntryException("分录不能为空")

        for line in entry.lines:
            if not line.foreign_currency:
                raise UnknownCurrencyException(f"分录行 {line.line_number} 未指定币种")
            if line.foreign_currency not in self.currency_registry:
                raise UnknownCurrencyException(f"未知币种：{line.foreign_currency}")

        period = self.periods.get(entry.period_key)
        if not period or not period.is_open:
            raise PeriodClosedForNormalEntryException(
                f"会计期间 {entry.period_key} 已关闭，禁止普通入账"
            )

        entry.status = EntryStatus.POSTED
        entry.posted_by = posted_by
        entry.posted_at = date.today()

    # ---------- 结算与折换 ----------

    def convert_foreign_to_local(self, amount_foreign: Decimal,
                                  foreign_currency: str,
                                  effective_date: date) -> Decimal:
        rate = self.get_exchange_rate(foreign_currency, effective_date)
        converted = amount_foreign * rate
        return round(converted, 2)

    def settle_journal_entry(self, entry: JournalEntry,
                              settlement_date: date,
                              settle_type: SettlementType,
                              settle_foreign_amount: Optional[Decimal] = None) -> Settlement:
        entry_id = entry.entry_id
        if entry_id not in self.journal_entries:
            raise JournalEntryInvalidException(f"分录 {entry_id} 不存在")
        if entry.status != EntryStatus.POSTED:
            raise JournalEntryInvalidException(f"只能对已过期账的分录进行结算，当前状态：{entry.status.value}")

        foreign_lines = [l for l in entry.lines if l.foreign_currency != self.base_currency]
        local_lines = [l for l in entry.lines if l.foreign_currency == self.base_currency]

        if not foreign_lines and not local_lines:
            raise JournalEntryInvalidException("分录不含可结算的外币或本位币行")

        # 收集应结算的外币总额
        total_foreign_debit = sum(abs(l.amount_foreign) for l in foreign_lines if l.is_debit)
        total_foreign_credit = sum(abs(l.amount_foreign) for l in foreign_lines if l.is_credit)

        if settle_type == SettlementType.PARTIAL:
            if settle_foreign_amount is None:
                raise SettlementOverdueException("部分结算必须指定结算金额")
            settle_foreign_amount = abs(settle_foreign_amount)
            settle_type = SettlementType.PARTIAL
        else:
            if settle_foreign_amount is None:
                settle_foreign_amount = max(total_foreign_debit, total_foreign_credit)

        settle_amount_local = self.convert_foreign_to_local(
            settle_foreign_amount, self.base_currency, settlement_date
        )

        settlement_id = f"S{self._settlement_counter:06d}"
        self._settlement_counter += 1
        settlement = Settlement(
            settlement_id=settlement_id,
            entry_id=entry_id,
            original_amount_foreign=max(total_foreign_debit, total_foreign_credit),
            original_amount_local=self.convert_foreign_to_local(
                max(total_foreign_debit, total_foreign_credit),
                self.base_currency, settlement_date
            ),
            settled_amount_foreign=settle_foreign_amount,
            settled_amount_local=settle_amount_local,
            settlement_date=settlement_date,
            settlement_type=settle_type,
            remaining_foreign=max(total_foreign_debit, total_foreign_credit) - settle_foreign_amount,
            remaining_local=self.convert_foreign_to_local(
                max(total_foreign_debit, total_foreign_credit) - settle_foreign_amount,
                self.base_currency, settlement_date
            ),
            completed=False
        )
        self.settlements[settlement_id] = settlement
        return settlement

    # ---------- 红字冲销 ----------

    def write_off_journal_entry(self, entry: JournalEntry,
                                 effective_date: date,
                                 off_set_amount: Optional[Decimal] = None) -> List["JournalEntryLine"]:
        if entry.status not in [EntryStatus.POSTED, EntryStatus.DRAFT]:
            raise JournalEntryInvalidException(f"只能对冲销已过期账的分录")

        if entry.status == EntryStatus.POSTED and off_set_amount is None:
            off_set_amount = abs(entry.total_debit)  # 全额冲销

        offset_lines: List["JournalEntryLine"] = []

        # 按照原分录方向相反构造冲销行
        for line in entry.lines:
            sign = Decimal("-1") if line.is_debit else Decimal("1")
            new_line = JournalEntryLine(
                line_number=len(offset_lines) + 1,
                account_code=line.account_code,
                amount_local=sign * abs(line.amount_local),
                amount_foreign=sign * line.amount_foreign,
                foreign_currency=line.foreign_currency,
                description=f"冲销 {entry.entry_number}"
            )
            offset_lines.append(new_line)

        # 重新打包为新分录
        entry_new = JournalEntry(
            entry_id=f"W{self._entry_counter + 1:06d}",
            entry_number=f"W{entry.entry_number}",
            entry_date=effective_date,
            period_key=entry.period_key,
            lines=offset_lines,
            description=f"红字冲销 {entry.entry_number}"
        )
        self.journal_entries[entry_new.entry_id] = entry_new

        return offset_lines

    # ---------- 尾差处理 ----------

    def process_fx_variance(self, entry: JournalEntry,
                              variance_date: date,
                              variance_amount: Decimal) -> Tuple[str, Decimal]:
        """
        将尾差计入汇兑损益科目。
        若为正数记入汇兑收益（贷方），负数记入汇兑损失（借方）。
        """
        fx_account = Account(
            account_code="6900",
            account_name="汇兑损益",
            account_type=AccountType.EXPENSE,
            currency=Currency(code=self.base_currency, name="本位币", symbol="$")
        )
        if fx_account.account_code not in self.accounts:
            self.register_account(fx_account)

        adjusted_amount = abs(variance_amount)
        line_number = len(entry.lines) + 1

        if variance_amount > Decimal("0"):
            # 收益：贷方
            gain_line = JournalEntryLine(
                line_number=line_number,
                account_code=fx_account.account_code,
                amount_local=-adjusted_amount,
                amount_foreign=Decimal("0"),
                foreign_currency=self.base_currency,
                description="尾差-汇兑收益"
            )
        else:
            # 损失：借方
            loss_line = JournalEntryLine(
                line_number=line_number,
                account_code=fx_account.account_code,
                amount_local=adjusted_amount,
                amount_foreign=Decimal("0"),
                foreign_currency=self.base_currency,
                description="尾差-汇兑损失"
            )
            gain_line = loss_line

        entry.lines.append(gain_line)
        entry._recalculate_totals()
        return fx_account.account_code, adjusted_amount

    # ---------- 结算超额检测 ----------

    def validate_settlement_limit(self, settlement: Settlement,
                                   pending_amount: Decimal):
        if pending_amount > abs(settlement.remaining_foreign):
            raise SettlementOverdueException(
                f"结算超额：待结算 {pending_amount} > 剩余 {settlement.remaining_foreign}"
            )

    # ---------- 批量处理工具 ----------

    def batch_validate_entries(self, entries: List[JournalEntry]) -> List[Tuple[JournalEntry, str]]:
        errors = []
        for entry in entries:
            if not entry.is_balanced():
                errors.append((entry, JournalEntryInvalidException(
                    f"分录 {entry.entry_id} 借贷不平"
                )))
            for line in entry.lines:
                if not line.foreign_currency:
                    errors.append((entry, UnknownCurrencyException(f"分录 {entry.entry_id} 缺少币种")))
                if line.foreign_currency not in self.currency_registry:
                    errors.append((entry, UnknownCurrencyException(f"分录 {entry.entry_id}: 未知币种 {line.foreign_currency}")))

        return errors

    def compute_total_fx_gain_loss(self, entries: List[JournalEntry],
                                    effective_date: date) -> Decimal:
        total = Decimal("0")
        for entry in entries:
            for line in entry.lines:
                if line.foreign_currency != self.base_currency:
                    continue
                foreign = 0
                for fl in [l for l in entry.lines if l.foreign_currency != self.base_currency]:
                    foreign += fl.amount_foreign
                if foreign != 0:
                    local = self.convert_foreign_to_local(foreign, self.base_currency, effective_date)
                    total += line.amount_local - local
        return round(total, 2)


# ============================================================
# 示例用法（纯演示逻辑，不纳入测试）
# ============================================================

if __name__ == "__main__":
    manager = MultiCurrencySettlementManager(base_currency="CNY")

    # 注册币种
    manager.register_currency(Currency("CNY", "人民币", "¥"))
    manager.register_currency(Currency("USD", "美元", "$"))
    manager.register_currency(Currency("EUR", "欧元", "€"))

    # 注册账户
    manager.register_account(Account(
        account_code="1001", account_name="银行存款-工行",
        account_type=AccountType.ASSET,
        currency=Currency(code="CNY", name="人民币", symbol="¥"),
        balance=Decimal("100000.00")
    ))
    manager.register_account(Account(
        account_code="1002", account_name="银行存款-中行",
        account_type=AccountType.ASSET,
        currency=Currency(code="CNY", name="人民币", symbol="¥"),
        balance=Decimal("50000.00")
    ))
    manager.register_account(Account(
        account_code="2001", account_name="应收账款-US客户",
        account_type=AccountType.ASSET,
        currency=Currency(code="CNY", name="人民币", symbol="¥"),
        balance=Decimal("0.00")
    ))

    # 注册期间
    manager.register_period(AccountingPeriod(
        period_id="P202501", period_number=1, year=2025,
        start_date=date(2025, 1, 1), end_date=date(2025, 1, 31),
        is_closed=False
    ))

    # 注册汇率
    manager.register_rate("USD", "CNY", Decimal("7.2000"), date(2025, 1, 15))
    manager.register_rate("EUR", "CNY", Decimal("7.8500"), date(2025, 1, 15))

    # 创建一笔含外币的分录
    entry = manager.create_journal_entry(
        entry_number="000001",
        entry_date=date(2025, 1, 15),
        period_key="2025-01",
        description="出口销售收款"
    )
    entry.add_line(JournalEntryLine(
        line_number=1, account_code="1002", amount_local=Decimal("14400.00"),
        amount_foreign=Decimal("2000.00"), foreign_currency="CNY", description=""
    ))
    entry.add_line(JournalEntryLine(
        line_number=2, account_code="2001", amount_local=Decimal("-14400.00"),
        amount_foreign=Decimal("-2000.00"), foreign_currency="USD", description=""
    ))
    entry.add_line(JournalEntryLine(
        line_number=3, account_code="6001", amount_local=Decimal("0.00"),
        amount_foreign=Decimal("0.00"), foreign_currency="CNY", description="尾差行预留"
    ))

    manager.post_journal_entry(entry)

    # 结算
    settlement = manager.settle_journal_entry(
        entry, settlement_date=date(2025, 1, 20),
        settle_type=SettlementType.FULL, settle_foreign_amount=Decimal("2000.00")
    )
    print(f"结算结果：ID={settlement.settlement_id}, 结算外币={settlement.settled_amount_foreign}, "
          f"结算本位币={settlement.settled_amount_local}, 剩余={settlement.remaining_foreign}")

    # 红字冲销
    off_lines = manager.write_off_journal_entry(entry, effective_date=date(2025, 1, 25))
    print(f"冲销行数：{len(off_lines)}")

    # 尾差处理
    var_code, var_amt = manager.process_fx_variance(entry, variance_date=date(2025, 1, 20), variance_amount=Decimal("0.15"))
    print(f"尾差调整：科目={var_code}, 金额={var_amt}")
```