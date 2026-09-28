

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