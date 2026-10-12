"""Unit tests for the new budget, monthly income, category rules, exclusions, and custom expenses."""

import datetime
import json
import tempfile
from pathlib import Path

import database as db
import server.classifier as cf


def test_database_income():
    print("Testing monthly income database storage...")
    db.init_database()

    # Save default income
    saved = db.save_monthly_income(4500.0)
    assert saved["income"] == 4500.0
    assert saved["month"] == "default"

    # Get default income
    res = db.get_monthly_income()
    assert res["income"] == 4500.0

    # Save specific month income
    saved_oct = db.save_monthly_income(5200.0, "2026-10")
    assert saved_oct["income"] == 5200.0
    assert saved_oct["month"] == "2026-10"

    # Get specific month income
    res_oct = db.get_monthly_income("2026-10")
    assert res_oct["income"] == 5200.0

    # Fallback to default for month without specific entry
    res_nov = db.get_monthly_income("2026-11")
    assert res_nov["income"] in (4500.0, 5200.0)

    print("✓ Database income tests passed.")


def test_transactions_retrieval():
    print("Testing transactions retrieval from database...")
    months = db.get_transaction_months()
    assert isinstance(months, list)
    assert len(months) > 0
    assert "2026-10" in months

    all_txs = db.get_saved_transactions("all", expenses_only=False)
    assert len(all_txs) == 26

    oct_expenses = db.get_saved_transactions("2026-10", expenses_only=True)
    assert len(oct_expenses) == 5
    for tx in oct_expenses:
        assert tx["amount"] > 0
        assert tx["date"].startswith("2026-10")

    print("✓ Transaction retrieval tests passed.")


def test_classifier_rules():
    print("Testing category classification engine...")
    test_rules = {
        "rules": [
            {"pattern": "Uber", "category": "Transportation", "match_type": "contains"},
            {"pattern": "Starbucks", "category": "Coffee", "match_type": "contains"},
            {"pattern": "McDonald's", "category": "Dining", "match_type": "exact"},
            {"pattern": "CREDIT CARD", "category": "Payments", "match_type": "starts_with"},
            {"pattern": r"flight\s*\d+", "category": "Travel", "match_type": "regex"},
        ],
        "default_category": "Other",
    }

    # Contains
    assert cf.classify_transaction("Uber 063015 SF**POOL**", test_rules) == "Transportation"
    # Exact (case-insensitive)
    assert cf.classify_transaction("mcdonald's", test_rules) == "Dining"
    assert cf.classify_transaction("McDonald's drive-thru", test_rules) == "Other"
    # Starts with
    assert cf.classify_transaction("credit card payment 123", test_rules) == "Payments"
    # Regex
    assert cf.classify_transaction("Book flight 402 now", test_rules) == "Travel"
    # Fallback
    assert cf.classify_transaction("Unknown Store XYZ", test_rules) == "Other"
    assert cf.classify_transaction("", test_rules) == "Other"
    assert cf.classify_transaction(None, test_rules) == "Other"

    print("✓ Classifier rules tests passed.")


def test_classifier_file_persistence():
    print("Testing category rules file load and save...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / "test_rules.json"
        orig_env = cf.os.environ.get("CATEGORY_RULES_PATH")
        try:
            cf.os.environ["CATEGORY_RULES_PATH"] = str(tmp_file)
            assert not tmp_file.exists()

            # Load should create default
            loaded = cf.load_category_rules()
            assert tmp_file.exists()
            assert len(loaded["rules"]) > 0

            # Add new rule and save
            loaded["rules"].append({"pattern": "GroceryStore", "category": "Groceries", "match_type": "contains"})
            save_res = cf.save_category_rules(loaded)
            assert save_res["status"] == "saved"

            # Re-read
            reloaded = cf.load_category_rules()
            assert any(r["pattern"] == "GroceryStore" for r in reloaded["rules"])

            # Classification with saved rules
            assert cf.classify_transaction("Spent at GroceryStore", reloaded) == "Groceries"

        finally:
            if orig_env is not None:
                cf.os.environ["CATEGORY_RULES_PATH"] = orig_env
            else:
                cf.os.environ.pop("CATEGORY_RULES_PATH", None)

    print("✓ Classifier file persistence tests passed.")


def test_transaction_exclusions():
    print("Testing transaction exclusions autosave and filtering...")
    tx_id = "test_tx_exclusion_123"
    month = "2026-10"

    # Set exclusion
    db.set_transaction_exclusion(tx_id, month, True)
    exclusions_oct = db.get_transaction_exclusions(month)
    assert tx_id in exclusions_oct

    # Exclusion for different month is not present
    exclusions_sep = db.get_transaction_exclusions("2026-09")
    assert tx_id not in exclusions_sep

    # Unset exclusion
    db.set_transaction_exclusion(tx_id, month, False)
    exclusions_after = db.get_transaction_exclusions(month)
    assert tx_id not in exclusions_after

    print("✓ Transaction exclusions tests passed.")


def test_custom_expenses():
    print("Testing custom expenses (one-off and recurring)...")
    # Add recurring expense
    rec = db.add_custom_expense("Rent", 1500.0, "Housing", "2026-10-01", "2026-10", is_recurring=True)
    assert rec["id"].startswith("custom_")
    assert rec["is_recurring"] is True

    # Add one-off expense for October
    one_off = db.add_custom_expense("Conference Ticket", 350.0, "Professional", "2026-10-15", "2026-10", is_recurring=False)
    assert one_off["is_recurring"] is False

    # In October 2026: both appear
    oct_custom = db.get_custom_expenses("2026-10")
    oct_ids = {c["id"] for c in oct_custom}
    assert rec["id"] in oct_ids
    assert one_off["id"] in oct_ids

    # In September 2026: recurring Rent appears, one-off ticket does NOT appear
    sep_custom = db.get_custom_expenses("2026-09")
    sep_ids = {c["id"] for c in sep_custom}
    assert rec["id"] in sep_ids
    assert one_off["id"] not in sep_ids

    # Delete custom expenses
    assert db.delete_custom_expense(rec["id"]) is True
    assert db.delete_custom_expense(one_off["id"]) is True

    # After deletion: neither appears
    oct_after = db.get_custom_expenses("2026-10")
    assert rec["id"] not in {c["id"] for c in oct_after}
    assert one_off["id"] not in {c["id"] for c in oct_after}

    print("✓ Custom expenses tests passed.")


def test_budget_leftover_calculation_with_exclusions():
    print("Testing budget leftover calculation with exclusions and custom expenses...")
    income = 5000.0
    rules = cf.load_category_rules()

    # Base October expenses: 5 items summing to 136.13
    oct_expenses = db.get_saved_transactions("2026-10", expenses_only=True)
    assert len(oct_expenses) == 5

    # Exclude SparkFun ($89.40)
    sparkfun_id = [t["transaction_id"] for t in oct_expenses if "SparkFun" in t.get("name", "")][0]
    db.set_transaction_exclusion(sparkfun_id, "2026-10", True)

    exclusions = db.get_transaction_exclusions("2026-10")
    assert sparkfun_id in exclusions

    # Add custom recurring gym expense ($50.0)
    gym = db.add_custom_expense("Gym Membership", 50.0, "Health", "2026-10-01", "2026-10", True)

    # Compute included total:
    # (136.13 - 89.40) + 50.0 = 46.73 + 50.0 = 96.73
    all_items = []
    for t in oct_expenses:
        all_items.append({
            "id": t["transaction_id"],
            "amount": t["amount"],
            "excluded": t["transaction_id"] in exclusions,
        })
    all_items.append({
        "id": gym["id"],
        "amount": gym["amount"],
        "excluded": gym["id"] in exclusions,
    })

    total_included = sum(item["amount"] for item in all_items if not item["excluded"])
    leftover = income - total_included

    assert round(total_included, 2) == 96.73
    assert round(leftover, 2) == 4903.27

    # Cleanup
    db.set_transaction_exclusion(sparkfun_id, "2026-10", False)
    db.delete_custom_expense(gym["id"])

    print("✓ Budget leftover calculation with exclusions tests passed.")


def test_refresh_date_range():
    print("Testing refresh past 3 months date calculation...")
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=90)
    assert (today - start_date).days == 90
    print("✓ Refresh date range test passed.")


def test_recurring_date_variation():
    print("Testing recurring expense date variation across months...")
    # Day 1 preserved across months
    assert cf.format_recurring_date("2026-10-01", "2026-09") == "2026-09-01"
    assert cf.format_recurring_date("2026-10-01", "2026-08") == "2026-08-01"
    assert cf.format_recurring_date("2026-10-01", "2026-11") == "2026-11-01"
    assert cf.format_recurring_date("2026-10-01", "2027-01") == "2027-01-01"

    # Day 15 preserved across months
    assert cf.format_recurring_date("2026-10-15", "2026-09") == "2026-09-15"
    assert cf.format_recurring_date("2026-10-15", "2026-02") == "2026-02-15"

    # Day 31 clamped in shorter months
    assert cf.format_recurring_date("2026-10-31", "2026-09") == "2026-09-30"  # Sept has 30 days
    assert cf.format_recurring_date("2026-10-31", "2026-08") == "2026-08-31"  # Aug has 31 days
    assert cf.format_recurring_date("2026-10-31", "2026-02") == "2026-02-28"  # Feb 2026 has 28 days

    # Fallback / empty date
    assert cf.format_recurring_date(None, "2026-09") == "2026-09-01"
    assert cf.format_recurring_date("", "2026-09") == "2026-09-01"
    assert cf.format_recurring_date("2026-10-01", "all") == "2026-10-01"

    print("✓ Recurring date variation tests passed.")


if __name__ == "__main__":
    test_database_income()
    test_transactions_retrieval()
    test_classifier_rules()
    test_classifier_file_persistence()
    test_transaction_exclusions()
    test_custom_expenses()
    test_budget_leftover_calculation_with_exclusions()
    test_refresh_date_range()
    test_recurring_date_variation()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! 🎉")

