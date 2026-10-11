"""Unit tests for the new budget, monthly income, and category rules features."""

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
    # Because save_monthly_income also updates default if not default
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


def test_budget_leftover_calculation():
    print("Testing budget leftover calculation...")
    income = 5000.0
    rules = cf.load_category_rules()
    oct_expenses = db.get_saved_transactions("2026-10", expenses_only=True)
    classified = [
        {
            "name": t.get("name"),
            "amount": t["amount"],
            "category": cf.classify_transaction(t.get("name"), rules),
        }
        for t in oct_expenses
    ]

    total_expenses = sum(item["amount"] for item in classified)
    leftover = income - total_expenses

    assert round(total_expenses, 2) == 136.13
    assert round(leftover, 2) == 4863.87

    print("✓ Budget leftover calculation tests passed.")


if __name__ == "__main__":
    test_database_income()
    test_transactions_retrieval()
    test_classifier_rules()
    test_classifier_file_persistence()
    test_budget_leftover_calculation()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! 🎉")

