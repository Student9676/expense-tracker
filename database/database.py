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

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id                TEXT PRIMARY KEY,
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
    """Create the tables and indexes if they do not exist yet."""
    with connect() as connection:
        connection.executescript(SCHEMA)


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


def build_transaction_row(transaction: Any, saved_at: str) -> dict[str, Any] | None:
    """Flatten one Plaid transaction into a table row, or None if it has no ID."""
    if not isinstance(transaction, dict):
        return None

    transaction_id = clean_text(transaction.get("transaction_id"))
    if transaction_id is None:
        return None

    location = as_dict(transaction.get("location"))
    payment_meta = as_dict(transaction.get("payment_meta"))
    finance_category = as_dict(transaction.get("personal_finance_category"))

    return {
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
) -> int:
    """Delete pending transactions that Plaid has replaced or dropped.

    A pending transaction disappears once it posts, and the posted transaction has a
    new ID that points back at it through ``pending_transaction_id``. Without this
    cleanup both rows would stay and the amount would be counted twice. Pending rows
    inside the fetched date range that Plaid no longer returns were cancelled.
    """
    stale_ids = set(superseded_ids)

    in_range = connection.execute(
        "SELECT transaction_id FROM transactions "
        "WHERE pending = 1 AND date BETWEEN ? AND ?",
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    stale_ids.update(row["transaction_id"] for row in in_range if row["transaction_id"] not in returned_ids)

    removed = 0
    for transaction_id in stale_ids:
        cursor = connection.execute(
            "DELETE FROM transactions WHERE transaction_id = ? AND pending = 1",
            (transaction_id,),
        )
        removed += cursor.rowcount
    return removed


def save_transactions(transactions: list[Any], start_date: date, end_date: date) -> dict[str, int]:
    """Save every transaction Plaid returned for the date range.

    Safe to run repeatedly: transactions are matched by ``transaction_id`` and updated
    in place. Everything happens in one database transaction, so a failure part-way
    through saves nothing. Returns counts describing what happened.
    """
    saved_at = utc_now()
    inserted = 0
    updated = 0
    skipped = 0
    returned_ids: set[str] = set()
    superseded_ids: set[str] = set()

    with connect() as connection:
        for transaction in transactions:
            row = build_transaction_row(transaction, saved_at)
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
            connection, superseded_ids - returned_ids, returned_ids, start_date, end_date
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
