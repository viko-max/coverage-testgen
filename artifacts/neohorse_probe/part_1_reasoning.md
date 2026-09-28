用户要求实现一个完整可运行的多币种复式分录结算器。需要包含：

1. 账户、会计期间、汇率表、分录行
2. 规则：
   - 同币种入账
   - 跨币种按汇率折到本位币
   - 红字冲销
   - 部分结清
   - 尾差进汇兑损益
   - 关账后只允许调整分录
3. 异常：借贷不平、关账后普通入账、未知币种、汇率缺失、结算超额都要抛出不同异常
4. 代码要长、分支要多，不要省略函数体
5. 只输出 ```python 代码块，不写测试

我需要设计一个完整的系统。让我思考数据结构：

- Account: 账户类
- AccountingPeriod: 会计期间类
- ExchangeRate: 汇率表
- JournalEntryLine: 分录行
- JournalEntry: 分录
- Settlement: 结算

需要的异常类：
- JournalEntryInvalidException (借贷不平)
- PeriodClosedForNormalEntryException (关账后普通入账)
- UnknownCurrencyException (未知币种)
- ExchangeRateMissingException (汇率缺失)
- SettlementOverdueException (结算超额)

核心逻辑：
1. 创建分录
2. 验证借贷平衡
3. 验证期间状态
4. 处理跨币种转换
5. 处理红字冲销
6. 处理部分结清
7. 计算尾差进汇兑损益
8. 结算

让我写一个完整的实现。代码要长，分支要多。

我会使用类来组织，包含多种验证逻辑和分支。

```python
import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

# ========== 异常定义 ==========
class AccountingError(Exception):
    """会计基础异常"""
    pass

class JournalEntryInvalidException(AccountingError):
    """借贷不平异常"""
    pass

class PeriodClosedForNormalEntryException(AccountingError):
    """关账后普通入账异常"""
    pass

class UnknownCurrencyException(AccountingError):
    """未知币种异常"""
    pass

class ExchangeRateMissingException(AccountingError):
    """汇率缺失异常"""
    pass

class SettlementOverdueException(AccountingError):
    """结算超额异常"""
    pass

class InvalidJournalEntryException(AccountingError):
    """无效分录异常"""
    pass

class DuplicateAccountException(AccountingError):
    """重复账户异常"""
    pass

# ========== 枚举定义 ==========
class AccountType(Enum):
    ASSET = "资产"
    LIABILITY = "负债"
    EQUITY = "所有者权益"
    REVENUE = "收入"
    EXPENSE = "费用"

class TransactionDirection(Enum):
    CREDIT = "贷方"
    DEBIT = "借方"

# ========== 数据类 ==========
@dataclass
class Currency:
    code: str
    name: str
    symbol: str = ""
    
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
    
    def __post_init__(self):
        if not self.account_code:
            raise ValueError("账户编号不能为空")
        if not self.account_name:
            raise ValueError("账户名称不能为空")
        if not self.currency or not self.currency.code:
            raise ValueError("币种不能为空")

@dataclass
class AccountingPeriod:
    period_id: str
    period_number: int  # 如 1-12
    year: int
    start_date: date
    end_date: date
    is_closed: bool = False
    is_adjusted: bool = False
    description: str = ""
    
    @property
    def period_key(self) -> str:
        return f"{self.year}-{self.period_number:02d}"

@dataclass
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_date: date
    
@dataclass 
class ExchangeRatesTable:
    base_currency: str
    rates: Dict[str, Dict[date, Decimal]] = field(default_factory=dict)
    
    def get_rate(self, quote_currency: str, target_currency: str, 
                  effective_date: date, precision: int = 6) -> Decimal:
        """获取汇率，如果找不到则抛异常"""
        if quote_currency == target_currency:
            return Decimal("1")
        
        # 尝试直接查找
        if quote_currency in self.rates:
            if effective_date in self.rates[quote_currency]:
                return round(self.rates[quote_currency][effective_date], precision)
        
        # 通过本位币中转
        if quote_currency in self.rates and target_currency in self.rates:
            if effective_date in self.rates[quote_currency]:
                rate_from_base = self.rates[quote_currency][effective_date]
            else:
                # 找最近日期
                rate_from_base = self._get_nearest_rate(effective_date, self.rates[quote_currency])
            if effective_date in self.rates[target_currency]:
                rate_to_base = self.rates[target_currency][effective_date]
            else:
                rate_to_base = self._get_nearest_rate(effective_date, self.rates[target_currency])
            if rate_from_base != 0:
                return round(Decimal("1") / rate_to_base * rate_from_base, precision)
        
        raise ExchangeRateMissingException(
            f"无法找到 {quote_currency} 对 {target_currency} 在 {effective_date} 的汇率"
        )
    
    def _get_nearest_rate(self, target_date: date, available_rates: Dict[date, Decimal]) -> Decimal:
        """获取最接近日期的汇率"""
        if not available_rates:
            raise ExchangeRateMissingException(f"没有可用的汇率数据")
        closest_date = min(available_rates.keys(), key=lambda d: abs((d - target_date).days))
        return available_rates[closest_date]
    
    def add_rate(self, quote_currency: str, target_currency: str, rate: Decimal, 
                 effective_date: date):
        """添加汇率"""
        if quote_currency not in self.rates:
            self.rates[quote_currency] = {}
        self.rates[quote_currency][effective_date] = round(rate, 6)

@dataclass
class JournalEntryLine:
    line_number: int
    account_code: str
    amount_local: Decimal  # 本位币金额
    amount_foreign: Decimal  # 外币金额
    foreign_currency: str   # 外币代码
    description: str = ""
    
@dataclass  
class JournalEntry:
    entry_id: str
    entry_number: str
    entry_date: date
    period_key: str
    lines: List[JournalEntryLine]
    status: str = "DRAFT"  # DRAFT, POSTED, CLOSED
    description: str = ""
    created_by: str = ""
    posted_by: str = ""
    posted_date: Optional[date] = None
    total_debit_local: Decimal = Decimal("0")
    total_credit_local: Decimal = "0"
    
    def validate_balance(self) -> bool:
        debit_sum = sum(line.amount_local for line in self.lines if line.amount_local > 0)
        credit_sum = sum(line.amount_local for line in self.lines if line.amount_local < 0)
        return abs(debit_sum + credit_sum) < Decimal("0.0000001")
```

我需要继续完成整个系统。让我考虑更多的细节：

1. 结算器应该处理多个分录行的结算
2. 需要支持红字冲销（负数金额）
3. 部分结清
4. 尾差进汇兑损益
5. 各种验证规则

让我重新组织代码，使其更完整。我会把代码写得更长，包含更多分支。

关键点：
- JournalEntryLine 应该有 amount_original 和 amount_converted
- 结算时需要计算实际结算金额
- 尾差处理

让我写出完整的代码。

我还需要设计 Settlement 类来处理结算过程。

另外需要注意：
- 借贷不平检查
- 关账后只能做调整分录
- 未知币种检查
- 汇率缺失检查
- 结算超额检查

让我开始写完整的代码。

关于结构：
1. 异常类
2. 枚举类
3. 数据类（Currency, Account, AccountingPeriod, ExchangeRate, ExchangeRatesTable, JournalEntryLine, JournalEntry, Settlement）
4. MultiCurrencySettlementManager（主管理类）

我需要确保代码很长、分支很多。

对于 JournalEntry，我需要区分本位币和外币。通常分录以本位币记账，外币金额按汇率转换。

结算器的主要功能：
1. 验证分录合法性
2. 转换外币为本位币
3. 计算借贷平衡
4. 处理结算
5. 处理尾差
6. 生成汇兑损益

让我编写完整的代码。

```python
import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

# ==================== 异常定义 ====================
class AccountingError(Exception):
    """会计系统基础异常"""
    pass

class JournalEntryInvalidException(AccountingError):
    """借贷不平异常：分录借方和贷方金额不相等"""
    pass

class PeriodClosedForNormalEntryException(AccountingError):
    """关账后普通入账异常：已关闭的会计期间不允许进行普通业务分录"""
    pass

class UnknownCurrencyException(AccountingError):
    """未知币种异常：系统中不存在该货币代码"""
    pass

class ExchangeRateMissingException(AccountingError):
    """汇率缺失异常：找不到指定日期或可用日期的汇率"""
    pass

class SettlementOverdueException(AccountingError):
    """结算超额异常：结算金额超过待结算总额"""
    pass

class InsufficientFundsException(AccountingError):
    """余额不足异常：账户余额不足以完成结算"""
    pass

class DuplicateAccountException(AccountingError):
    """重复账户异常：同一账户在同一分录中出现多次且方向相同"""
    pass

class InvalidDateException(AccountingError):
    """无效日期异常：日期不符合业务规则"""
    pass

class NegativeAmountException(AccountingError):
    """负数金额异常：单笔分录金额不能为负"""
    pass

class EmptyJournalEntryException(AccountingError):
    """空分录异常：分录中至少需要一行"""
    pass

class UnsupportedCurrencyException(AccountingError):
    """不支持的币种异常：该币种不在系统支持的范围内"""
    pass

# ==================== 枚举定义 ====================
class AccountType(Enum):
    ASSET = "资产"
    LIABILITY = "负债"
    EQUITY = "所有者权益"
    REVENUE = "收入"
    EXPENSE = "费用"
    INCOME_TAX = "所得税"
    OTHER = "其他"

class TransactionDirection(Enum):
    CREDIT = "贷方"
    DEBIT = "借方"

class EntryStatus(Enum):
    DRAFT = "未过账"
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
    FOREIGN_EXCHANGE_GAIND = "汇兑收益"
    FOREIGN_EXCHANGE_LOSS = "汇兑损失"

# ==================== 数据类定义 ====================
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
    
    def is_within_period(self, check_date: date) -> bool:
        return self.start_date <= check_date <= self.end_date

@dataclass
class ExchangeRate:
    quote_currency: str          # 计价币种
    base_currency: str           # 基准币种
    rate: Decimal               # 汇率值
    effective_date: date        # 生效日期
    source: str = ""             # 数据来源
    
@dataclass
class ExchangeRatesTable:
    base_currency: str
    rates: Dict[str, Dict[date, Decimal]] = field(default_factory=dict)
    
    def get_rate(self, quote_currency: str, target_currency: str, 
                  effective_date: date, precision: int = 6) -> Decimal:
        """
        获取汇率：quote_currency 转换为 target_currency 的汇率
        
        如果 quote_currency == target_currency，返回 1
        如果直接能找到汇率，返回该汇率
        否则通过基准币种中转计算
        """
        if quote_currency == target_currency:
            return Decimal("1")
        
        if not self.rates:
            raise ExchangeRateMissingException(
                f"汇率表中没有任何汇率数据，quote={quote_currency}, target={target_currency}"
            )
        
        # 检查是否有直接汇率
        if quote_currency in self.rates and target_currency in self.rates[quote_currency]:
            if effective_date in self.rates[quote_currency][target_currency]:
                return round(self.rates[quote_currency][target_currency][effective_date], precision)
        
        # 通过基准币种中转：rate(quote->base) / rate(target->base)
        if quote_currency in self.rates and target_currency in self.rates:
            rate_quote_to_base = self._get_rate_on_or_before(effective_date, quote_currency, self.base_currency)
            rate_target_to_base = self._get_rate_on_or_before(effective_date, target_currency, self.base_currency)
            if rate_quote_to_base != Decimal("0") and rate_target_to_base != Decimal("0"):
                result = rate_quote_to_base / rate_target_to_base
                return round(result, precision)
        
        raise ExchangeRateMissingException(
            f"无法找到 {quote_currency} 对 {target_currency} 在 {effective_date} 的汇率。\n"
            f"可用币种：{', '.join(self.rates.keys())}"
        )
    
    def _get_rate_on_or_before(self, target_date: date, quote_currency: str, 
                               base_currency: str) -> Decimal:
        """获取目标日期当日或之前最近的汇率"""
        if quote_currency not in self.rates:
            raise ExchangeRateMissingException(
                f"币种 {quote_currency} 没有汇率记录"
            )
        available_dates = list(self.rates[quote_currency].keys())
        if not available_dates:
            raise ExchangeRateMissingException(
                f"币种 {quote_currency} 没有任何汇率数据"
            )
        
        # 寻找 <= target_date 的最新日期
        candidate_dates = [d for d in available_dates if d <= target_date]
        if not candidate_dates:
            raise ExchangeRateMissingException(
                f"币种 {quote_currency} 没有找到 {target_date} 及之前的汇率"
            )
        
        latest_date = max(candidate_dates)
        return self.rates[quote_currency][latest_date]
    
    def add_rate(self, quote_currency: str, base_currency: str, rate: Decimal, 
                 effective_date: date):
        """添加一条汇率记录"""
        if not self.rates.get(quote_currency):
            self.rates[quote_currency] = {}
        self.rates[quote_currency][base_currency] = {
            effective_date: round(rate, 6)
        }
    
    def update_rate(self, quote_currency: str, base_currency: str, rate: Decimal, 
                    effective_date: date):
        """更新或添加汇率"""
        if quote_currency not in self.rates:
            self.rates[quote_currency] = {}
        self.rates[quote_currency][base_currency][effective_date] = round(rate, 6)

@dataclass
class JournalEntryLine:
    line_number: int
    account_code: str
    amount_local: Decimal     # 本位币金额
    amount_foreign: Decimal   # 外币金额
    foreign_currency: str     # 外币代码
    description: str = ""
    reference: str = ""       # 参考号
    
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
    lines: List[JournalEntryLine] = field(default_factory=list)
    status: EntryStatus = EntryStatus.DRAFT
    description: str = ""
    created_by: str = ""
    created_at: Optional[date] = None
    posted_by: str = ""
    posted_at: Optional[date] = None
    
    # 校验用
    _total_debit: Decimal = Decimal("0")
    _total_credit: Decimal = Decimal("0")
    
    @property
    def total_debit(self) -> Decimal:
        return self._total_debit
    
    @property
    def total_credit(self) -> Decimal:
        return self._total_credit
    
    def add_line(self, line: JournalEntryLine):
        """添加分录行"""
        if self.status != EntryStatus.DRAFT:
            raise JournalEntryInvalidException("只能在草稿状态下添加分录行")
        self.lines.append(line)
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
    
    def validate_balance(self) -> bool:
        """验证借贷是否平衡"""
        diff = abs(self._total_debit - self._total_credit)
        return diff < Decimal("0.0000001")
    
    def is_balanced(self) -> bool:
        return self.validate_balance()

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
```

继续写完 Settlement 类和主管理类的代码。这是关键的实现部分。

考虑到代码长度要求，我需要确保主管理类有足够的复杂度和分支。

让我完成整个代码的编写。

我需要处理以下逻辑：

1. 创建和验证分录
2. 外币转本位币
3. 借贷平衡验证
4. 期间状态检查
5. 红字冲销处理
6. 部分结算
7. 尾差进汇兑损益
8. 各种异常抛出

主类 `MultiCurrencySettlementManager` 应该包含：
- 初始化：账户、期间、汇率表
- 创建分录
- 结算分录
- 冲销分录
- 调整分录
- 验证方法

让我完整写出代码。

由于代码很长，我需要精心组织。我会尽量让每个函数都有实际内容，而不是简单的占位符。

关于红字冲销：红字冲销通常用负数表示，在分录中行可以用负金额。

关于部分结清：结算时可以设置 partial setlement，剩余部分继续结算。

关于尾差进汇兑损益：当外币折算和本位币之间有微小差异时，将差异计入汇兑损益科目。

现在让我开始写完整代码。

关键设计决策：
1. 所有金额使用 Decimal 类型保证精度
2. 本位币作为统一记账货币
3. 每笔分录有一个本位币汇总
4. 跨币种按汇率转换
5. 尾差自动调整到汇兑损益

让我开始编写最终代码。
