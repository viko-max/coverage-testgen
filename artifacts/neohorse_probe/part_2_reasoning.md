The user wants me to write pytest tests for the multi-currency double-entry settlement manager. I need at least 24 test functions, numbered test_01 through test_24+. Each test should cover specific scenarios and be runnable directly.

Let me plan the tests:

1. test_01 - 同币种平衡入账 (same currency balanced entry)
2. test_02 - 借贷不平异常 (unequal debit/credit)
3. test_03 - 未知币种异常 (unknown currency)
4. test_04 - 汇率缺失异常 (missing exchange rate)
5. test_05 - 跨币种折算 (cross-currency conversion)
6. test_06 - 汇兑损益 (foreign exchange gain/loss)
7. test_07 - 红字冲销 (red-letter reversal)
8. test_08 - 部分结清 (partial settlement)
9. test_09 - 结算超额 (settlement overage)
10. test_10 - 关账 (period close)
11. test_11 - 关账后拒绝普通分录 (reject normal entries after close)
12. test_12 - 关账后允许调整分录 (allow adjustment entries after close)

I need at least 24 tests, so I'll split these into multiple tests each. Let me think about more granular tests:

1. test_01 - 同币种借方入账
2. test_02 - 同币种贷方入账
3. test_03 - 同币种平衡入账（收）
4. test_04 - 同币种平衡入账（付）
5. test_05 - 借贷不平抛出异常
6. test_06 - 未知币种抛出异常
7. test_07 - 汇率缺失抛出异常
8. test_08 - 跨币种按汇率折到本位币
9. test_09 - 跨币种尾差进汇兑损益
10. test_10 - 红字冲销生成反向分录
11. test_11 - 部分结清剩余金额计算
12. test_12 - 全额结清完成标记
13. test_13 - 结算超额抛出异常
14. test_14 - 关账前普通入账成功
15. test_15 - 会计期间不存在异常
16. test_16 - 日期不在期间范围内异常
17. test_17 - 关账后拒绝普通分录
18. test_18 - 关账后允许调整分录
19. test_19 - 空分录抛出异常
20. test_20 - 同一账户同一侧重复抛出异常
21. test_21 - 负数金额抛出异常
22. test_22 - 分录行序号重复抛出异常
23. test_23 - 已过期账的结算限制
24. test_24 - 多币种混合结算

Let me write the complete pytest file. I'll reuse the same classes from the previous implementation since the user said "不要重写实现" (don't rewrite the implementation). I need to import from the previous module. Actually, since this is a separate file, I should either put all code in one file or assume the previous code exists as a module. Given the instruction "正文只输出一个 ```python 代码块", I think I should write a standalone pytest file that includes the necessary imports. But the user says "不要重写实现" - so I should not duplicate the implementation. Let me write the pytest file with a minimal stub that imports from the previous module, but since we can't have two files in one code block, I'll write the complete thing including the class definitions needed for testing, but mark them as reusable. Actually, re-reading: "不要重写实现。只写 pytest" - the user wants pytest tests only, no reimplementation. I'll create a single file that has both the model class (reused from before) and the tests. Since it's one code block, I need to include everything.

Actually wait - the user said "不要重写实现" which means don't rewrite the implementation. But since I need a complete runnable file, I think I should just write the tests and import from a hypothetical module. However, to make it runnable directly, I might need to include the classes. Let me think... The safest approach: write the complete file with the model class (copy-pasted from before, no changes) + all 24+ tests. That satisfies "正文只输出一个 ```python 代码块" and makes it directly runnable.

Let me count carefully. I'll write at least 24 test functions.

Actually, let me reconsider. The user explicitly said "不要重写实现" - don't rewrite the implementation. This suggests they want me to only write tests. But for a standalone runnable pytest file, if I don't include the implementation, it won't run. The most practical interpretation: write a pytest file that contains the tests, and if needed, include the model classes inline so it's runnable standalone. Given the constraints, I'll include the model classes (copied from the previous answer, unchanged) plus the tests.

Wait, actually the key instruction: "只写 pytest，至少 24 个测试函数". So the body should be pytest tests. Let me write the full thing. I'll copy the model class verbatim (no changes) and add the test functions. Let me make sure there are at least 24 tests.

Let me draft the tests:

test_01: 同币种平衡入账 - 借方和贷方同币种且相等
test_02: 同币种平衡入账（收入端）- 另一方向验证
test_03: 借贷不平抛出 JournalEntryInvalidException
test_04: 未知币种抛出 UnknownCurrencyException
test_05: 汇率缺失抛出 ExchangeRateMissingException
test_06: 跨币种按汇率折到本位币
test_07: 跨币种尾差进汇兑损益
test_08: 红字冲销生成反向分录
test_09: 部分结清剩余金额正确
test_010: 全额结清完成标记
test_011: 结算超额抛出 SettlementOverdueException
test_012: 关账前普通入账成功
test_013: 会计期间不存在抛出异常
test_014: 日期不在期间范围内抛出异常
test_015: 关账后拒绝普通分录
test_016: 关账后允许调整分录
test_017: 空分录抛出 EmptyJournalEntryException
test_018: 同一账户同一侧重复抛出 DuplicateAccountException
test_019: 分录行序号重复抛出异常
test_020: 负数金额抛出 NegativeAmountException
test_021: 草稿状态不能添加分录行
test_022: 未知币种在结算时也检测
test_023: 多币种混合入账与结算
test_024: 红字冲销后重新过账验证
test_025: 调整分录在关账后成功

That's 25 tests. Good.

Now let me write the code. I'll be careful about the structure. Since the user said "正文只输出一个 ```python 代码块", I must output exactly one code block.

Let me now write the actual code. I need to be careful about the imports and class names matching exactly with the previous implementation.

Actually, I realize I should match the exact class and function names from the previous answer. Let me review:

- AccountingError, JournalEntryInvalidException, PeriodClosedForNormalEntryException, UnknownCurrencyException, ExchangeRateMissingException, SettlementOverdueException, InsufficientFundsException, DuplicateAccountException, InvalidDateException, NegativeAmountException, EmptyJournalEntryException, UnsupportedCurrencyException, UnsupportedAdjustmentTypeException
- AccountType, EntryStatus, SettlementType, AdjustmentType
- Currency, Account, AccountingPeriod, ExchangeRate, ExchangeRatesTable, JournalEntryLine, JournalEntry, Settlement
- MultiCurrencySettlementManager

Test functions should use pytest.raises with the exception classes.

Let me write this out now.

One thing to note: the previous answer had some issues I shouldn't fix since I'm told not to rewrite. But for tests, I should test what was actually implemented. The `process_fx_variance` method in the previous answer creates lines on the entry and recalculates totals. It doesn't check balance first though - that's fine for testing.

Also, `write_off_journal_entry` creates new entries but doesn't post them automatically - that's fine.

Let me write the tests now. I need to be very careful about the exact signatures and behavior.

One issue: in the previous implementation, `post_journal_entry` checks `if not period or not period.is_open` and raises `PeriodClosedForNormalEntryException`. For adjustment after close, `adjust_journal_entry` doesn't check `is_open`. Let me verify my tests align.

Also, the `settle_journal_entry` method checks `if entry.status != EntryStatus.POSTED` and raises `JournalEntryInvalidException`. 

OK let me write the complete file now.
