"""SQLite storage for Plaid transactions.

Conventions
-----------
* Every column except ``transaction_id`` is nullable. Plaid returns null for many
  fields, so a missing, null, empty or whitespace-only value is always stored as
  NULL. Queries only ever need ``IS NULL`` / ``COALESCE``, never ``= ''``.
* Money is stored twice: ``amount`` (REAL, convenient for quick sums and charts) and
  ``amount_cents`` (INTEGER, exact, for sums that must not drift). Both keep the sign
  exactly as Plaid reports it: positive = money leaving the account (a purchase),
  negative = money coming in (a refund, deposit or payment received).
* Dates and datetimes are stored as ISO 8601 text, which SQLite's date functions
  (``strftime``, ``date``) understand directly.
* The complete original transaction is kept in ``raw_json`` so nothing Plaid returns
  is lost, including fields that do not have a column of their own.
* Nested objects are flattened into prefixed columns (``location_*``,
  ``payment_meta_*``, ``pfc_*``). ``counterparties`` is a list, so it lives in its
  own table.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id                TEXT PRIMARY KEY,
    item_id                       TEXT,
    account_id                    TEXT,
    account_owner                 TEXT,
    amount                        REAL,
    amount_cents                  INTEGER,
    iso_currency_code             TEXT,
    unofficial_currency_code      TEXT,
    date                          TEXT,
    datetime                      TEXT,
    authorized_date               TEXT,
    authorized_datetime           TEXT,
    name                          TEXT,
    merchant_name                 TEXT,
    merchant_entity_id            TEXT,
    merchant_category_code        TEXT,
    logo_url                      TEXT,
    website                       TEXT,
    payment_channel               TEXT,
    transaction_type              TEXT,
    transaction_code              TEXT,
    check_number                  TEXT,
    pending                       INTEGER,
    pending_transaction_id        TEXT,
    category                      TEXT,
    category_id                   TEXT,
    pfc_primary                   TEXT,
    pfc_detailed                  TEXT,
    pfc_confidence_level          TEXT,
    pfc_version                   TEXT,
    pfc_icon_url                  TEXT,
    location_address              TEXT,
    location_city                 TEXT,
    location_region               TEXT,
    location_postal_code          TEXT,
    location_country              TEXT,
    location_lat                  REAL,
    location_lon                  REAL,
    location_store_number         TEXT,
    payment_meta_reference_number TEXT,
    payment_meta_ppd_id           TEXT,
    payment_meta_payee            TEXT,
    payment_meta_by_order_of      TEXT,
    payment_meta_payer            TEXT,
    payment_meta_payment_method   TEXT,
    payment_meta_payment_processor TEXT,
    payment_meta_reason           TEXT,
    running_balance               TEXT,
    raw_json                      TEXT NOT NULL,
    first_saved_at                TEXT NOT NULL,
    last_saved_at                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date);
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions (account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_pfc_primary ON transactions (pfc_primary);

-- One row per connected bank (a Plaid "item"). The access token is NOT stored here;
-- it lives in the macOS Keychain under this item_id.
CREATE TABLE IF NOT EXISTS plaid_items (
    item_id          TEXT PRIMARY KEY,
    institution_id   TEXT,
    institution_name TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transaction_counterparties (
    transaction_id   TEXT NOT NULL REFERENCES transactions (transaction_id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    name             TEXT,
    type             TEXT,
    website          TEXT,
    logo_url         TEXT,
    confidence_level TEXT,
    entity_id        TEXT,
    phone_number     TEXT,
    PRIMARY KEY (transaction_id, position)
);

CREATE TABLE IF NOT EXISTS monthly_income (
    month            TEXT PRIMARY KEY,
    amount           REAL NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transaction_exclusions (
    transaction_id   TEXT NOT NULL,
    month            TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (transaction_id, month)
);

CREATE TABLE IF NOT EXISTS custom_expenses (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    amount           REAL NOT NULL,
    category         TEXT,
    date             TEXT,
    month            TEXT,
    is_recurring     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""

COUNTERPARTY_FIELDS = (
    "name",
    "type",
    "website",
    "logo_url",
    "confidence_level",
    "entity_id",
    "phone_number",
)


def get_database_path() -> Path:
    """Return the database file path. Read lazily so values from .env are picked up."""
    configured = os.getenv("DATABASE_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).with_name("expense_tracker.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection that commits on success, rolls back on error, then closes."""
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_database() -> None:
    """Create the tables and indexes if they do not exist yet, and upgrade older databases."""
    with connect() as connection:
        connection.executescript(SCHEMA)
        # Databases created before multi-bank support have no item_id column.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(transactions)")}
        if "item_id" not in columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN item_id TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_item_id ON transactions (item_id)"
        )


# --- Value normalization -----------------------------------------------------


def clean_text(value: Any) -> str | None:
    """Return trimmed text, or None for null, empty and whitespace-only values."""
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text or None


def to_decimal(value: Any) -> Decimal | None:
    """Parse a number or numeric string into a finite Decimal, or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        # str() of a float gives its shortest exact form (89.4 -> "89.4"), which
        # avoids binary float noise such as 89.4 * 100 == 8940.000000000001.
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def to_float(value: Any) -> float | None:
    number = to_decimal(value)
    if number is None:
        return None
    result = float(number)
    return result if math.isfinite(result) else None


def to_amount_cents(value: Any) -> int | None:
    """Convert an amount to integer hundredths (cents), rounding half up."""
    number = to_decimal(value)
    if number is None:
        return None
    return int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_bool_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if value in (0, 1):
        return int(value)
    return None


def to_json_text(value: Any) -> str | None:
    """Serialize lists and objects to JSON text. Null and empty values become NULL."""
    if value is None or value == [] or value == {}:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def as_dict(value: Any) -> dict:
    """Treat anything that is not an object (such as null) as an empty object."""
    return value if isinstance(value, dict) else {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_transaction_row(
    transaction: Any, saved_at: str, item_id: str | None = None
) -> dict[str, Any] | None:
    """Flatten one Plaid transaction into a table row, or None if it has no ID."""
    if not isinstance(transaction, dict):
        return None

    transaction_id = clean_text(transaction.get("transaction_id"))
    if transaction_id is None:
        return None

    location = as_dict(transaction.get("location"))
    payment_meta = as_dict(transaction.get("payment_meta"))
    finance_category = as_dict(transaction.get("personal_finance_category"))

    row = {
        "transaction_id": transaction_id,
        "account_id": clean_text(transaction.get("account_id")),
        "account_owner": clean_text(transaction.get("account_owner")),
        "amount": to_float(transaction.get("amount")),
        "amount_cents": to_amount_cents(transaction.get("amount")),
        "iso_currency_code": clean_text(transaction.get("iso_currency_code")),
        "unofficial_currency_code": clean_text(transaction.get("unofficial_currency_code")),
        "date": clean_text(transaction.get("date")),
        "datetime": clean_text(transaction.get("datetime")),
        "authorized_date": clean_text(transaction.get("authorized_date")),
        "authorized_datetime": clean_text(transaction.get("authorized_datetime")),
        "name": clean_text(transaction.get("name")),
        "merchant_name": clean_text(transaction.get("merchant_name")),
        "merchant_entity_id": clean_text(transaction.get("merchant_entity_id")),
        "merchant_category_code": clean_text(transaction.get("merchant_category_code")),
        "logo_url": clean_text(transaction.get("logo_url")),
        "website": clean_text(transaction.get("website")),
        "payment_channel": clean_text(transaction.get("payment_channel")),
        "transaction_type": clean_text(transaction.get("transaction_type")),
        "transaction_code": clean_text(transaction.get("transaction_code")),
        "check_number": clean_text(transaction.get("check_number")),
        "pending": to_bool_int(transaction.get("pending")),
        "pending_transaction_id": clean_text(transaction.get("pending_transaction_id")),
        "category": to_json_text(transaction.get("category")),
        "category_id": clean_text(transaction.get("category_id")),
        "pfc_primary": clean_text(finance_category.get("primary")),
        "pfc_detailed": clean_text(finance_category.get("detailed")),
        "pfc_confidence_level": clean_text(finance_category.get("confidence_level")),
        "pfc_version": clean_text(finance_category.get("version")),
        "pfc_icon_url": clean_text(transaction.get("personal_finance_category_icon_url")),
        "location_address": clean_text(location.get("address")),
        "location_city": clean_text(location.get("city")),
        "location_region": clean_text(location.get("region")),
        "location_postal_code": clean_text(location.get("postal_code")),
        "location_country": clean_text(location.get("country")),
        "location_lat": to_float(location.get("lat")),
        "location_lon": to_float(location.get("lon")),
        "location_store_number": clean_text(location.get("store_number")),
        "payment_meta_reference_number": clean_text(payment_meta.get("reference_number")),
        "payment_meta_ppd_id": clean_text(payment_meta.get("ppd_id")),
        "payment_meta_payee": clean_text(payment_meta.get("payee")),
        "payment_meta_by_order_of": clean_text(payment_meta.get("by_order_of")),
        "payment_meta_payer": clean_text(payment_meta.get("payer")),
        "payment_meta_payment_method": clean_text(payment_meta.get("payment_method")),
        "payment_meta_payment_processor": clean_text(payment_meta.get("payment_processor")),
        "payment_meta_reason": clean_text(payment_meta.get("reason")),
        "running_balance": to_json_text(transaction.get("running_balance")),
        "raw_json": json.dumps(transaction, ensure_ascii=False, sort_keys=True, default=str),
        "first_saved_at": saved_at,
        "last_saved_at": saved_at,
    }
    # Only set item_id when known, so re-saving without it never erases an existing value.
    if item_id is not None:
        row["item_id"] = item_id
    return row


def build_counterparty_rows(transaction: dict, transaction_id: str) -> list[dict[str, Any]]:
    """Flatten the counterparties list. Entries that are not objects are ignored."""
    counterparties = transaction.get("counterparties")
    if not isinstance(counterparties, list):
        return []

    rows = []
    for position, counterparty in enumerate(counterparties):
        if not isinstance(counterparty, dict):
            continue
        row = {field: clean_text(counterparty.get(field)) for field in COUNTERPARTY_FIELDS}
        rows.append({"transaction_id": transaction_id, "position": position, **row})
    return rows


# --- Saving ------------------------------------------------------------------


def _upsert_transaction(connection: sqlite3.Connection, row: dict[str, Any]) -> bool:
    """Insert or update one transaction. Returns True if it already existed."""
    existed = (
        connection.execute(
            "SELECT 1 FROM transactions WHERE transaction_id = ?",
            (row["transaction_id"],),
        ).fetchone()
        is not None
    )

    columns = list(row)
    placeholders = ", ".join(f":{column}" for column in columns)
    # Keep the original first_saved_at when a transaction is saved again.
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in columns
        if column not in ("transaction_id", "first_saved_at")
    )
    connection.execute(
        f"INSERT INTO transactions ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT (transaction_id) DO UPDATE SET {updates}",
        row,
    )
    return existed


def _replace_counterparties(
    connection: sqlite3.Connection, transaction_id: str, rows: list[dict[str, Any]]
) -> None:
    connection.execute(
        "DELETE FROM transaction_counterparties WHERE transaction_id = ?",
        (transaction_id,),
    )
    for row in rows:
        columns = list(row)
        connection.execute(
            f"INSERT INTO transaction_counterparties ({', '.join(columns)}) "
            f"VALUES ({', '.join(f':{column}' for column in columns)})",
            row,
        )


def _remove_stale_pending(
    connection: sqlite3.Connection,
    superseded_ids: set[str],
    returned_ids: set[str],
    start_date: date,
    end_date: date,
    item_id: str | None = None,
) -> int:
    """Delete pending transactions that Plaid has replaced or dropped.

    A pending transaction disappears once it posts, and the posted transaction has a
    new ID that points back at it through ``pending_transaction_id``. Without this
    cleanup both rows would stay and the amount would be counted twice. Pending rows
    inside the fetched date range that Plaid no longer returns were cancelled.

    When ``item_id`` is given only that bank's rows are considered. Without this, syncing
    one bank would delete every other bank's pending transactions, since Plaid only
    returns the bank that was asked for.
    """
    stale_ids = set(superseded_ids)

    query = "SELECT transaction_id FROM transactions WHERE pending = 1 AND date BETWEEN ? AND ?"
    params: list[Any] = [start_date.isoformat(), end_date.isoformat()]
    if item_id is not None:
        query += " AND item_id = ?"
        params.append(item_id)
    in_range = connection.execute(query, params).fetchall()
    stale_ids.update(row["transaction_id"] for row in in_range if row["transaction_id"] not in returned_ids)

    removed = 0
    for transaction_id in stale_ids:
        cursor = connection.execute(
            "DELETE FROM transactions WHERE transaction_id = ? AND pending = 1",
            (transaction_id,),
        )
        removed += cursor.rowcount
    return removed


def save_transactions(
    transactions: list[Any],
    start_date: date,
    end_date: date,
    item_id: str | None = None,
) -> dict[str, int]:
    """Save every transaction Plaid returned for the date range.

    Safe to run repeatedly: transactions are matched by ``transaction_id`` and updated
    in place. Everything happens in one database transaction, so a failure part-way
    through saves nothing. Returns counts describing what happened.

    ``item_id`` identifies the bank the transactions came from. It is stored on every row
    and limits the stale-pending cleanup to that bank.
    """
    saved_at = utc_now()
    inserted = 0
    updated = 0
    skipped = 0
    returned_ids: set[str] = set()
    superseded_ids: set[str] = set()

    with connect() as connection:
        for transaction in transactions:
            row = build_transaction_row(transaction, saved_at, item_id)
            if row is None:
                skipped += 1
                continue

            if _upsert_transaction(connection, row):
                updated += 1
            else:
                inserted += 1
            _replace_counterparties(
                connection,
                row["transaction_id"],
                build_counterparty_rows(transaction, row["transaction_id"]),
            )

            returned_ids.add(row["transaction_id"])
            if row["pending_transaction_id"]:
                superseded_ids.add(row["pending_transaction_id"])

        pending_removed = _remove_stale_pending(
            connection, superseded_ids - returned_ids, returned_ids, start_date, end_date, item_id
        )
        total = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    return {
        "fetched": len(transactions),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "pending_removed": pending_removed,
        "total_in_database": total,
    }


# --- Connected banks ----------------------------------------------------------


def upsert_plaid_item(
    item_id: str, institution_id: str | None, institution_name: str | None
) -> dict[str, Any]:
    """Register a connected bank, or refresh its name if it is already registered."""
    clean_item = clean_text(item_id)
    if not clean_item:
        raise ValueError("item_id is required")
    name = clean_text(institution_name) or "Connected bank"
    now = utc_now()
    with connect() as connection:
        connection.execute(
            "INSERT INTO plaid_items (item_id, institution_id, institution_name, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (item_id) DO UPDATE SET "
            "institution_id = excluded.institution_id, institution_name = excluded.institution_name",
            (clean_item, clean_text(institution_id), name, now),
        )
        row = connection.execute(
            "SELECT item_id, institution_id, institution_name, created_at "
            "FROM plaid_items WHERE item_id = ?",
            (clean_item,),
        ).fetchone()
    return dict(row)


def get_plaid_items() -> list[dict[str, Any]]:
    """Return every connected bank, oldest first, with how many transactions it has."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT i.item_id, i.institution_id, i.institution_name, i.created_at, "
            "(SELECT COUNT(*) FROM transactions t WHERE t.item_id = i.item_id) AS transaction_count "
            "FROM plaid_items i ORDER BY i.created_at, i.item_id"
        ).fetchall()
        return [dict(row) for row in rows]


def backfill_transaction_item_id(item_id: str) -> int:
    """Assign a bank to saved transactions that predate multi-bank support."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE transactions SET item_id = ? WHERE item_id IS NULL", (item_id,)
        )
        return cursor.rowcount


def delete_plaid_item(item_id: str) -> None:
    """Forget a connected bank (its transactions are kept; see delete_item_transactions)."""
    with connect() as connection:
        connection.execute("DELETE FROM plaid_items WHERE item_id = ?", (item_id,))


def delete_item_transactions(item_id: str) -> int:
    """Delete every saved transaction that came from one bank, plus its exclusions."""
    with connect() as connection:
        connection.execute(
            "DELETE FROM transaction_exclusions WHERE transaction_id IN "
            "(SELECT transaction_id FROM transactions WHERE item_id = ?)",
            (item_id,),
        )
        cursor = connection.execute("DELETE FROM transactions WHERE item_id = ?", (item_id,))
        return cursor.rowcount


def count_transactions_by_account() -> dict[str, int]:
    """How many transactions are saved for each Plaid account_id."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT account_id, COUNT(*) AS n FROM transactions GROUP BY account_id"
        ).fetchall()
        return {row["account_id"]: row["n"] for row in rows}


# --- Monthly Income & Querying -----------------------------------------------


def get_monthly_income(month: str | None = None) -> dict[str, Any]:
    """Retrieve saved monthly income for a given month or fall back to default."""
    clean_m = clean_text(month)
    with connect() as connection:
        if clean_m and clean_m.lower() != "all":
            row = connection.execute(
                "SELECT month, amount, updated_at FROM monthly_income WHERE month = ?",
                (clean_m,),
            ).fetchone()
            if row:
                return {
                    "month": row["month"],
                    "income": float(row["amount"]),
                    "updated_at": row["updated_at"],
                }

        # Check default entry
        row = connection.execute(
            "SELECT month, amount, updated_at FROM monthly_income WHERE month = 'default'"
        ).fetchone()
        if row:
            return {
                "month": clean_m or "default",
                "income": float(row["amount"]),
                "updated_at": row["updated_at"],
            }

        # Check any most recently updated entry
        row = connection.execute(
            "SELECT month, amount, updated_at FROM monthly_income ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row:
            return {
                "month": clean_m or row["month"],
                "income": float(row["amount"]),
                "updated_at": row["updated_at"],
            }

        return {"month": clean_m or "default", "income": 0.0, "updated_at": None}


def save_monthly_income(amount: float, month: str | None = None) -> dict[str, Any]:
    """Save monthly income for a specific month or as default."""
    now = utc_now()
    clean_m = clean_text(month)
    if clean_m and clean_m.lower() == "all":
        clean_m = "default"
    key = clean_m or "default"

    with connect() as connection:
        connection.execute(
            "INSERT INTO monthly_income (month, amount, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (month) DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at",
            (key, float(amount), now),
        )
        if key != "default":
            connection.execute(
                "INSERT INTO monthly_income (month, amount, updated_at) VALUES ('default', ?, ?) "
                "ON CONFLICT (month) DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at",
                (float(amount), now),
            )

    return {"month": key, "income": float(amount), "updated_at": now}


def get_saved_transactions(
    month: str | None = None, expenses_only: bool = False
) -> list[dict[str, Any]]:
    """Retrieve saved transactions from the database with optional month and expense filtering."""
    query = (
        "SELECT t.transaction_id, t.item_id, i.institution_name, t.name, t.merchant_name, "
        "t.amount, t.amount_cents, t.iso_currency_code, t.date, t.datetime, t.category, "
        "t.pfc_primary, t.pfc_detailed "
        "FROM transactions t LEFT JOIN plaid_items i ON i.item_id = t.item_id"
    )
    clauses: list[str] = []
    params: list[Any] = []

    clean_m = clean_text(month)
    if clean_m and clean_m.lower() != "all":
        clauses.append("strftime('%Y-%m', t.date) = ?")
        params.append(clean_m)

    if expenses_only:
        clauses.append("t.amount > 0")

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY t.date DESC, t.transaction_id DESC"

    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_transaction_months() -> list[str]:
    """Return all distinct YYYY-MM months with transactions or custom expenses in descending order."""
    with connect() as connection:
        rows_tx = connection.execute(
            "SELECT DISTINCT strftime('%Y-%m', date) as m FROM transactions "
            "WHERE date IS NOT NULL"
        ).fetchall()
        rows_custom = connection.execute(
            "SELECT DISTINCT month as m FROM custom_expenses "
            "WHERE month IS NOT NULL AND month != ''"
        ).fetchall()
        months_set = {r["m"] for r in rows_tx if r["m"]} | {r["m"] for r in rows_custom if r["m"]}
        return sorted(months_set, reverse=True)


# --- Transaction Exclusions --------------------------------------------------


def get_transaction_exclusions(month: str | None = None) -> set[str]:
    """Return set of excluded transaction IDs for a specific month (or all months)."""
    clean_m = clean_text(month)
    with connect() as connection:
        if clean_m and clean_m.lower() != "all":
            rows = connection.execute(
                "SELECT transaction_id FROM transaction_exclusions WHERE month = ? OR month = 'all'",
                (clean_m,),
            ).fetchall()
            return {row["transaction_id"] for row in rows}
        else:
            rows = connection.execute(
                "SELECT transaction_id, month FROM transaction_exclusions"
            ).fetchall()
            result = set()
            for r in rows:
                if r["month"] == "all":
                    result.add(r["transaction_id"])
                result.add(f"{r['transaction_id']}::{r['month']}")
            return result



def set_transaction_exclusion(
    transaction_id: str, month: str | None, excluded: bool
) -> bool:
    """Set or remove exclusion for a transaction in a specific month."""
    clean_tx = clean_text(transaction_id)
    if not clean_tx:
        return False
    clean_m = clean_text(month) or "all"
    now = utc_now()
    with connect() as connection:
        if excluded:
            connection.execute(
                "INSERT OR IGNORE INTO transaction_exclusions (transaction_id, month, created_at) "
                "VALUES (?, ?, ?)",
                (clean_tx, clean_m, now),
            )
        else:
            connection.execute(
                "DELETE FROM transaction_exclusions WHERE transaction_id = ? AND (month = ? OR month = 'all')",
                (clean_tx, clean_m),
            )
    return True


# --- Custom Expenses ---------------------------------------------------------


def get_custom_expenses(month: str | None = None) -> list[dict[str, Any]]:
    """Return custom expenses for a given month or recurring ones."""
    clean_m = clean_text(month)
    query = (
        "SELECT id, name, amount, category, date, month, is_recurring, created_at, updated_at "
        "FROM custom_expenses"
    )
    params: list[Any] = []
    if clean_m and clean_m.lower() != "all":
        query += " WHERE is_recurring = 1 OR month = ?"
        params.append(clean_m)
    query += " ORDER BY date DESC, created_at DESC"

    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def add_custom_expense(
    name: str,
    amount: float,
    category: str | None = None,
    date_str: str | None = None,
    month: str | None = None,
    is_recurring: bool = False,
) -> dict[str, Any]:
    """Create a new custom expense."""
    clean_n = clean_text(name)
    if not clean_n:
        raise ValueError("Name cannot be empty")
    clean_amt = float(amount)
    clean_cat = clean_text(category)
    clean_d = clean_text(date_str)
    clean_m = clean_text(month)
    if not clean_m and clean_d:
        clean_m = clean_d[:7]
    rec_int = 1 if is_recurring else 0
    now = utc_now()
    item_id = f"custom_{uuid.uuid4().hex[:12]}"

    with connect() as connection:
        connection.execute(
            "INSERT INTO custom_expenses (id, name, amount, category, date, month, is_recurring, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, clean_n, clean_amt, clean_cat, clean_d, clean_m, rec_int, now, now),
        )

    return {
        "id": item_id,
        "name": clean_n,
        "amount": clean_amt,
        "category": clean_cat,
        "date": clean_d,
        "month": clean_m,
        "is_recurring": bool(rec_int),
        "created_at": now,
        "updated_at": now,
    }


def delete_custom_expense(custom_id: str) -> bool:
    """Delete a custom expense by its id."""
    clean_id = clean_text(custom_id)
    if not clean_id:
        return False
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM custom_expenses WHERE id = ?",
            (clean_id,),
        )
        connection.execute(
            "DELETE FROM transaction_exclusions WHERE transaction_id = ?",
            (clean_id,),
        )
        return cursor.rowcount > 0


def update_custom_expense(
    custom_id: str,
    name: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    date_str: str | None = None,
    is_recurring: bool | None = None,
) -> dict[str, Any] | None:
    """Update an existing custom expense."""
    clean_id = clean_text(custom_id)
    if not clean_id:
        return None
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM custom_expenses WHERE id = ?",
            (clean_id,),
        ).fetchone()
        if not row:
            return None

        current = dict(row)
        n = clean_text(name) if name is not None else current["name"]
        a = float(amount) if amount is not None else current["amount"]
        c = clean_text(category) if category is not None else current["category"]
        d = clean_text(date_str) if date_str is not None else current["date"]
        rec = (
            (1 if is_recurring else 0)
            if is_recurring is not None
            else current["is_recurring"]
        )
        now = utc_now()
        m = d[:7] if d else current["month"]

        connection.execute(
            "UPDATE custom_expenses SET name = ?, amount = ?, category = ?, date = ?, month = ?, is_recurring = ?, updated_at = ? WHERE id = ?",
            (n, a, c, d, m, rec, now, clean_id),
        )
        return {
            "id": clean_id,
            "name": n,
            "amount": a,
            "category": c,
            "date": d,
            "month": m,
            "is_recurring": bool(rec),
            "updated_at": now,
        }


