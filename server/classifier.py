"""Classification engine for transactions based on editable/exportable rules."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RULES = {
    "rules": [
        {"pattern": "Uber", "category": "Transportation", "match_type": "contains"},
        {"pattern": "Lyft", "category": "Transportation", "match_type": "contains"},
        {"pattern": "McDonald's", "category": "Dining & Food", "match_type": "contains"},
        {"pattern": "Starbucks", "category": "Coffee & Cafes", "match_type": "contains"},
        {"pattern": "SparkFun", "category": "Electronics & Tech", "match_type": "contains"},
        {"pattern": "CREDIT CARD", "category": "Bills & Payments", "match_type": "contains"},
        {"pattern": "United Airlines", "category": "Travel", "match_type": "contains"},
        {"pattern": "INTRST PYMNT", "category": "Banking & Fees", "match_type": "contains"},
        {"pattern": "Amazon", "category": "Shopping", "match_type": "contains"},
        {"pattern": "Target", "category": "Groceries & Supplies", "match_type": "contains"},
        {"pattern": "Walmart", "category": "Groceries & Supplies", "match_type": "contains"},
        {"pattern": "Netflix", "category": "Subscriptions & Entertainment", "match_type": "contains"},
        {"pattern": "Spotify", "category": "Subscriptions & Entertainment", "match_type": "contains"},
    ],
    "default_category": "Uncategorized",
}


def get_rules_file_path() -> Path:
    """Return the path to the category rules file."""
    configured = os.getenv("CATEGORY_RULES_PATH")
    if configured:
        return Path(configured)
    # Default to category_rules.json in the repository root
    return Path(__file__).resolve().parent.parent / "category_rules.json"


def normalize_rules_data(data: Any) -> dict[str, Any]:
    """Ensure data follows the standard {rules: [...], default_category: str} structure."""
    if isinstance(data, list):
        rules_list = data
        default_cat = "Uncategorized"
    elif isinstance(data, dict):
        rules_list = data.get("rules", [])
        default_cat = data.get("default_category", "Uncategorized") or "Uncategorized"
    else:
        return json.loads(json.dumps(DEFAULT_RULES))

    cleaned_rules = []
    for item in rules_list:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern", "")).strip()
        category = str(item.get("category", "")).strip()
        if not pattern or not category:
            continue
        match_type = str(item.get("match_type", "contains")).strip().lower()
        if match_type not in ("contains", "exact", "starts_with", "regex"):
            match_type = "contains"
        cleaned_rules.append(
            {
                "pattern": pattern,
                "category": category,
                "match_type": match_type,
            }
        )

    return {
        "rules": cleaned_rules,
        "default_category": str(default_cat).strip() or "Uncategorized",
    }


def load_category_rules() -> dict[str, Any]:
    """Read the category rules from disk, initializing if missing."""
    rules_path = get_rules_file_path()
    if not rules_path.exists():
        normalized = json.loads(json.dumps(DEFAULT_RULES))
        try:
            rules_path.parent.mkdir(parents=True, exist_ok=True)
            rules_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not create category rules file at %s: %s", rules_path, exc)
        return normalized

    try:
        content = rules_path.read_text(encoding="utf-8")
        raw = json.loads(content)
        return normalize_rules_data(raw)
    except Exception as exc:
        logger.error("Error reading category rules file from %s: %s", rules_path, exc)
        return json.loads(json.dumps(DEFAULT_RULES))


def save_category_rules(data: Any) -> dict[str, Any]:
    """Validate and write category rules to disk."""
    normalized = normalize_rules_data(data)
    rules_path = get_rules_file_path()
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return {
        "status": "saved",
        "count": len(normalized["rules"]),
        "rules": normalized["rules"],
        "default_category": normalized["default_category"],
    }


def classify_transaction(name: str | None, rules_data: dict[str, Any] | None = None) -> str:
    """Classify a transaction name into a category using the rule set."""
    if not name or not str(name).strip():
        default = (rules_data or {}).get("default_category", "Uncategorized")
        return str(default)

    clean_name = str(name).strip()
    data = rules_data if rules_data is not None else load_category_rules()
    rules = data.get("rules", [])
    default_category = data.get("default_category", "Uncategorized") or "Uncategorized"

    for rule in rules:
        pattern = rule.get("pattern", "")
        category = rule.get("category", "")
        match_type = rule.get("match_type", "contains")

        if not pattern or not category:
            continue

        try:
            if match_type == "contains":
                if pattern.lower() in clean_name.lower():
                    return category
            elif match_type == "exact":
                if pattern.lower() == clean_name.lower():
                    return category
            elif match_type == "starts_with":
                if clean_name.lower().startswith(pattern.lower()):
                    return category
            elif match_type == "regex":
                if re.search(pattern, clean_name, re.IGNORECASE):
                    return category
        except Exception:
            continue

    return default_category

