import calendar
import datetime
import json
import os

import plaid
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File
from contextlib import asynccontextmanager
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from credentials import (
    get_api_credentials,
    save_access_token,
    get_access_token,
    get_item_access_token,
    item_token_account,
    delete_bank_access_tokens,
)
from database import (
    init_database,
    save_transactions,
    get_monthly_income,
    save_monthly_income,
    get_saved_transactions,
    get_transaction_months,
    get_transaction_exclusions,
    set_transaction_exclusion,
    get_custom_expenses,
    add_custom_expense,
    delete_custom_expense,
    update_custom_expense,
    get_plaid_items,
    upsert_plaid_item,
    backfill_transaction_item_id,
    delete_plaid_item,
    delete_item_transactions,
    count_transactions_by_account,
)
from server.classifier import (
    classify_transaction,
    load_category_rules,
    save_category_rules,
    get_rules_file_path,
    format_recurring_date,
)

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.access_tokens = {}

    # Create the Plaid client once during server startup
    try:
        client = create_plaid_client()
        app.state.plaid_client = client
    except Exception as e:
        # Handle keychain access and configuration errors gracefully
        print(f"Plaid client initialization failed: {e}")
        app.state.plaid_client = None

    # Create the database tables once during server startup
    try:
        init_database()
    except Exception as e:
        # Saving will fail until this is fixed, but the rest of the server still works
        print(f"Database initialization failed: {e}")

    # Load every connected bank's access token (needs the client and database above)
    try:
        load_bank_tokens(app)
    except Exception as e:
        # Handle keychain access errors gracefully
        print(f"Keychain access failed: {e}")

    yield  # Server starts running

    # Clear the tokens and client from memory on shutdown
    app.state.access_tokens = {}
    app.state.plaid_client = None

app = FastAPI(
    title="Expense Tracker Plaid Server",
    description="HTTP server for Plaid authentication and setup operations.",
    lifespan=lifespan,
)

PLAID_SERVICE_NAME = os.getenv("PLAID_SERVICE_NAME")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox").strip().lower()
PLAID_PRODUCTS = [
    product.strip()
    for product in os.getenv("PLAID_PRODUCTS", "transactions").split(",")
    if product.strip()
]
PLAID_COUNTRY_CODES = [
    country.strip()
    for country in os.getenv("PLAID_COUNTRY_CODES", "US").split(",")
    if country.strip()
]
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI") or None
# Only keep transactions from these Plaid account types, e.g. PLAID_ACCOUNT_TYPES=credit
# (types: depository, credit, loan, investment). Empty keeps every account.
PLAID_ACCOUNT_TYPES = [
    kind.strip().lower()
    for kind in os.getenv("PLAID_ACCOUNT_TYPES", "").split(",")
    if kind.strip()
]
# Temporary switch for re-linking a bank that is already connected: the old connection and
# its saved transactions are replaced by the new one. Turn it off again afterwards.
REPLACE_EXISTING_BANK = os.getenv("PLAID_REPLACE_EXISTING_BANK", "").strip().lower() in {"1", "true", "yes"}


def get_plaid_host():
    """Return the Plaid host configured for the current environment."""
    if PLAID_ENV == "sandbox":
        return plaid.Environment.Sandbox
    if PLAID_ENV == "production":
        return plaid.Environment.Production
    raise ValueError("PLAID_ENV must be 'sandbox' or 'production'")


def create_plaid_client():
    """Build a Plaid client from the API credentials stored in the keychain."""
    client_id, secret = get_api_credentials()
    configuration = plaid.Configuration(
        host=get_plaid_host(),
        api_key={
            "clientId": client_id,
            "secret": secret,
            "plaidVersion": "2020-09-14",
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def read_access_tokens() -> dict[str, str]:
    """Access tokens for every connected bank, keyed by Plaid item_id."""
    tokens = getattr(app.state, "access_tokens", None)
    if not tokens:
        raise HTTPException(
            status_code=500,
            detail="No bank is connected, or its access token could not be retrieved from the Keychain."
        )
    return tokens


def read_plaid_client() -> plaid_api.PlaidApi:
    client = getattr(app.state, "plaid_client", None)
    if not client:
        raise HTTPException(
            status_code=500,
            detail="Plaid client is missing or could not be created from the Keychain credentials."
        )
    return client


@app.get(
    "/",
    summary="Check server status",
    description="Confirm that the server is running.",
    status_code=200,
)
def health_check():
    """Return a simple server status response."""
    return {
        "status": "The server is active.",
    }


@app.get(
    "/api/connection_status",
    summary="Check whether an account is connected",
    description="Report whether an access token is already saved and loaded on the server.",
    status_code=200,
)
def connection_status():
    """Return whether an access token is available, without exposing it."""
    tokens = getattr(app.state, "access_tokens", None) or {}
    return {
        "connected": bool(tokens),
        "bank_count": len(tokens),
    }


@app.get(
    "/api/banks",
    summary="List connected banks and their accounts",
    description="Return every connected bank with the accounts Plaid has on it and how many transactions are saved for each. Access tokens are never returned.",
    status_code=200,
)
def list_banks():
    """Return the connected banks with their accounts."""
    plaid_client = getattr(app.state, "plaid_client", None)
    tokens = getattr(app.state, "access_tokens", None) or {}
    saved = count_transactions_by_account()

    banks = []
    for item in get_plaid_items():
        entry = {**item, "accounts": [], "accounts_error": None}
        token = tokens.get(item["item_id"])
        if not token:
            entry["accounts_error"] = "No access token was found in the Keychain for this bank."
        elif plaid_client is None:
            entry["accounts_error"] = "The Plaid client is unavailable."
        else:
            try:
                entry["accounts"] = [
                    {
                        "account_id": account["account_id"],
                        "name": account.get("name"),
                        "mask": account.get("mask"),
                        "type": account_type_of(account),
                        "subtype": str(getattr(account.get("subtype"), "value", account.get("subtype")) or ""),
                        "transaction_count": saved.get(account["account_id"], 0),
                        # False when PLAID_ACCOUNT_TYPES excludes this kind of account.
                        "tracked": not PLAID_ACCOUNT_TYPES or account_type_of(account) in PLAID_ACCOUNT_TYPES,
                    }
                    for account in list_accounts(plaid_client, token)
                ]
            except Exception as exc:
                entry["accounts_error"] = describe_sync_error(exc)
        banks.append(entry)
    return {"banks": banks}


@app.delete(
    "/api/banks/{item_id}",
    summary="Disconnect a bank",
    description="Remove the connection at Plaid, delete its access token from the Keychain and forget the bank. Saved transactions are kept unless delete_transactions is true.",
    status_code=200,
)
def remove_bank(item_id: str, delete_transactions: bool = False):
    """Disconnect one bank."""
    item = next((i for i in get_plaid_items() if i["item_id"] == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="That bank is not connected.")

    tokens = getattr(app.state, "access_tokens", None) or {}
    token = tokens.get(item_id)
    name = item["institution_name"]

    # 1) Remove it at Plaid first, so a failure leaves everything as it was.
    plaid_removed = False
    if token:
        plaid_client = getattr(app.state, "plaid_client", None)
        if plaid_client is None:
            raise HTTPException(
                status_code=500,
                detail="The Plaid client is unavailable, so nothing was deleted. Restart the server and try again.",
            )
        try:
            plaid_client.item_remove(ItemRemoveRequest(access_token=token))
            plaid_removed = True
        except Exception as exc:
            already_gone = (
                isinstance(exc, plaid.ApiException)
                and format_error(exc).get("error_code") == "ITEM_NOT_FOUND"
            )
            if not already_gone:
                raise HTTPException(
                    status_code=502,
                    detail=f"Plaid could not remove {name}: {describe_sync_error(exc)} Nothing was deleted.",
                )
            plaid_removed = True

    # 2) Delete the access token from the Keychain.
    warnings = []
    keychain_removed = False
    try:
        delete_bank_access_tokens(PLAID_SERVICE_NAME, PLAID_ENV, item_id, token)
        keychain_removed = True
    except Exception as exc:
        warnings.append(f"The bank was disconnected, but its Keychain entry could not be deleted: {exc}")

    # 3) Forget the bank (and optionally its saved transactions).
    transactions_deleted = delete_item_transactions(item_id) if delete_transactions else 0
    delete_plaid_item(item_id)
    tokens.pop(item_id, None)

    return {
        "status": "removed",
        "item_id": item_id,
        "institution_name": name,
        "plaid_removed": plaid_removed,
        "keychain_removed": keychain_removed,
        "transactions_deleted": transactions_deleted,
        "bank_count": len(tokens),
        "warnings": warnings,
    }


@app.get(
    "/api/debug/plaid",
    summary="Show what Plaid has for each connected bank",
    description="Diagnostic: the Link products configured, each connection's products, and every account Plaid returns with how many transactions are saved for it. Never returns access tokens.",
    status_code=200,
)
def debug_plaid(
    tokens: dict[str, str] = Depends(read_access_tokens),
    plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client),
):
    saved = count_transactions_by_account()
    names = {item["item_id"]: item["institution_name"] for item in get_plaid_items()}
    banks = []
    for item_id, access_token in tokens.items():
        entry = {"institution_name": names.get(item_id), "item_id": item_id}
        try:
            item = plaid_client.item_get(ItemGetRequest(access_token=access_token)).to_dict()["item"]
            entry["item"] = {
                key: item.get(key)
                for key in ("products", "billed_products", "consented_products", "available_products", "error")
            }
            entry["accounts"] = [
                {
                    "name": account.get("name"),
                    "mask": account.get("mask"),
                    "type": account_type_of(account),
                    "subtype": str(getattr(account.get("subtype"), "value", account.get("subtype"))),
                    "account_id": account["account_id"],
                    "transactions_saved": saved.get(account["account_id"], 0),
                }
                for account in list_accounts(plaid_client, access_token)
            ]
        except Exception as exc:
            entry["error"] = describe_sync_error(exc)
        banks.append(entry)
    return jsonable_encoder(
        {
            "link_products_configured": PLAID_PRODUCTS,
            "account_types_kept": PLAID_ACCOUNT_TYPES or "all",
            "replace_existing_bank": REPLACE_EXISTING_BANK,
            "banks": banks,
        }
    )


@app.post(
    "/api/initialize",
    summary="Initialize the Plaid client",
    description="Authenticate and initialize the shared Plaid client.",
    status_code=200,
)
def initialize_plaid_client():
    """Create the Plaid API client if it was not already created at startup."""
    was_initialized = getattr(app.state, "plaid_client", None) is not None
    if not was_initialized:
        client = create_plaid_client()
        app.state.plaid_client = client
    return {
        "status": "already initialized" if was_initialized else "initialized",
        "environment": PLAID_ENV,
    }


@app.post(
    "/api/create_link_token",
    summary="Create a Plaid Link token",
    description="Create a Link token for connecting a financial institution.",
    status_code=200,
)
def create_link_token(plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client)):
    """Receive a client request for a Plaid Link token and return it to the client."""
    link_request = LinkTokenCreateRequest(
        products=[Products(product) for product in PLAID_PRODUCTS],
        client_name="Expense Tracker",
        country_codes=[CountryCode(code) for code in PLAID_COUNTRY_CODES],
        language="en",
        user=LinkTokenCreateRequestUser(
            client_user_id="expense-tracker-user",
        ),
        redirect_uri=PLAID_REDIRECT_URI,
    )

    response = plaid_client.link_token_create(link_request)
    return response.to_dict()


def save_plaid_access_token(access_token, item_id):
    """Save one bank's Plaid access token in the keychain secrets manager."""
    service_name = os.getenv("PLAID_SERVICE_NAME")
    if not service_name:
        raise ValueError("PLAID_SERVICE_NAME is not configured in .env")

    save_access_token(
        "access_token",
        access_token,
        service_name,
        account=item_token_account(PLAID_ENV, item_id),
    )


def describe_item(plaid_client, access_token) -> dict:
    """Look up which bank an access token belongs to."""
    item = plaid_client.item_get(ItemGetRequest(access_token=access_token)).to_dict()["item"]
    institution_id = item.get("institution_id")
    name = None
    if institution_id:
        try:
            institution = plaid_client.institutions_get_by_id(
                InstitutionsGetByIdRequest(
                    institution_id=institution_id,
                    country_codes=[CountryCode(code) for code in PLAID_COUNTRY_CODES],
                )
            ).to_dict()["institution"]
            name = institution.get("name")
        except Exception as exc:
            print(f"Could not look up institution {institution_id}: {exc}")
    return {
        "item_id": item["item_id"],
        "institution_id": institution_id,
        "institution_name": name or "Connected bank",
    }


def load_bank_tokens(app) -> None:
    """Fill app.state.access_tokens from the Keychain for every registered bank."""
    migrate_legacy_access_token(app)

    tokens = {}
    for item in get_plaid_items():
        token = get_item_access_token(PLAID_SERVICE_NAME, PLAID_ENV, item["item_id"])
        if token:
            tokens[item["item_id"]] = token
        else:
            print(f"No access token in the Keychain for {item['institution_name']} ({item['item_id']}).")
    app.state.access_tokens = tokens


def migrate_legacy_access_token(app) -> None:
    """Adopt the single access token saved before multi-bank support as the first bank.

    The old Keychain entry is left untouched. Saved transactions that have no bank yet
    are assigned to it.
    """
    if get_plaid_items():
        return
    plaid_client = getattr(app.state, "plaid_client", None)
    if plaid_client is None:
        return
    legacy_token = get_access_token(PLAID_SERVICE_NAME, PLAID_ENV)
    if not legacy_token:
        return

    info = describe_item(plaid_client, legacy_token)
    save_plaid_access_token(legacy_token, info["item_id"])
    upsert_plaid_item(info["item_id"], info["institution_id"], info["institution_name"])
    moved = backfill_transaction_item_id(info["item_id"])
    print(f"Migrated existing connection to {info['institution_name']} ({moved} transactions assigned).")


# The client sends the public token after Plaid Link completes.
@app.post(
    "/api/set_access_token",
    summary="Exchange a Plaid public token",
    description="Exchange the Link public token, securely save the access token and add the bank to the connected banks. Connecting another bank adds to the existing ones.",
    status_code=200,
)
async def set_access_token(request: Request, plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client)):
    """Exchange the public token with Plaid and securely save the access token."""

    form = await request.form()
    public_token = form.get("public_token")
    if not public_token:
        return JSONResponse(
            content={"error": "public_token is required"},
            status_code=400,
        )

    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = plaid_client.item_public_token_exchange(exchange_request)
    access_token = response["access_token"]
    info = describe_item(plaid_client, access_token)

    # Linking the same bank twice would create a second item and duplicate every transaction.
    duplicate = next(
        (
            item
            for item in get_plaid_items()
            if info["institution_id"]
            and item["institution_id"] == info["institution_id"]
            and item["item_id"] != info["item_id"]
        ),
        None,
    )
    if duplicate and not REPLACE_EXISTING_BANK:
        try:
            plaid_client.item_remove(ItemRemoveRequest(access_token=access_token))
        except Exception as exc:
            print(f"Could not remove duplicate item {info['item_id']}: {exc}")
        return JSONResponse(
            content={
                "error": f"{duplicate['institution_name']} is already connected. To re-link it "
                "(for example to change which accounts are shared), set "
                "PLAID_REPLACE_EXISTING_BANK=true in .env and restart the server."
            },
            status_code=409,
        )
    if duplicate:
        # Replace the old connection: its transaction IDs would not match the new item's,
        # so keeping them would show every transaction twice.
        old_tokens = getattr(app.state, "access_tokens", None) or {}
        old_token = old_tokens.pop(duplicate["item_id"], None)
        if old_token:
            try:
                plaid_client.item_remove(ItemRemoveRequest(access_token=old_token))
            except Exception as exc:
                print(f"Could not remove old item {duplicate['item_id']} at Plaid: {exc}")
        try:
            delete_bank_access_tokens(PLAID_SERVICE_NAME, PLAID_ENV, duplicate["item_id"], old_token)
        except Exception as exc:
            print(f"Could not delete the old Keychain entry for {duplicate['item_id']}: {exc}")
        removed_rows = delete_item_transactions(duplicate["item_id"])
        delete_plaid_item(duplicate["item_id"])
        print(f"Replaced {duplicate['institution_name']}: removed {removed_rows} saved transactions.")

    save_plaid_access_token(access_token, info["item_id"])
    upsert_plaid_item(info["item_id"], info["institution_id"], info["institution_name"])
    tokens = getattr(app.state, "access_tokens", None) or {}
    tokens[info["item_id"]] = access_token
    app.state.access_tokens = tokens

    # Pull the new bank's recent history right away. Plaid can need a little while to
    # prepare a brand-new connection, so a failure here is reported, not raised; the
    # next refresh picks it up.
    start_date, end_date = default_sync_window()
    initial_sync = sync_bank(
        plaid_client, info["item_id"], access_token, info["institution_name"], start_date, end_date
    )[1]

    return {
        "status": "connected",
        "item_id": info["item_id"],
        "institution_name": info["institution_name"],
        "bank_count": len(tokens),
        "initial_sync": initial_sync,
    }


def fetch_all_transactions(
    plaid_client: plaid_api.PlaidApi,
    access_token: str,
    start_date: datetime.date,
    end_date: datetime.date,
):
    """Retrieve every transaction between two dates, following Plaid's pagination."""
    all_transactions = []
    offset = 0
    count = 500

    while True:
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions(
                count=count,
                offset=offset,
            ),
        )

        response = plaid_client.transactions_get(request).to_dict()

        transactions = response["transactions"]
        total_transactions = response["total_transactions"]

        all_transactions.extend(transactions)

        offset += len(transactions)
        # An empty page also ends the loop so it can never spin forever.
        if not transactions or len(all_transactions) >= total_transactions:
            break

    return all_transactions


def default_sync_window() -> tuple[datetime.date, datetime.date]:
    """The past 3 months (90 days)."""
    today = datetime.date.today()
    return today - datetime.timedelta(days=90), today


def describe_sync_error(exc: Exception) -> str:
    if isinstance(exc, plaid.ApiException):
        info = format_error(exc)
        return str(info.get("error_message") or info.get("error_code") or exc)
    return str(exc)


SYNC_COUNT_KEYS = ("fetched", "inserted", "updated", "skipped", "pending_removed")


def account_type_of(account: dict) -> str:
    kind = account.get("type")
    return str(getattr(kind, "value", kind) or "").lower()


def list_accounts(plaid_client, access_token) -> list[dict]:
    """The accounts Plaid has on one bank connection."""
    response = plaid_client.accounts_get(AccountsGetRequest(access_token=access_token)).to_dict()
    return response["accounts"]


def sync_bank(plaid_client, item_id, access_token, institution_name, start_date, end_date):
    """Fetch and save one bank's transactions. Never raises: failures are reported in the result.

    Returns (save_result or None, bank_status).
    """
    bank = {"item_id": item_id, "institution_name": institution_name}
    try:
        transactions = fetch_all_transactions(plaid_client, access_token, start_date, end_date)
        if PLAID_ACCOUNT_TYPES:
            allowed = {
                account["account_id"]
                for account in list_accounts(plaid_client, access_token)
                if account_type_of(account) in PLAID_ACCOUNT_TYPES
            }
            transactions = [t for t in transactions if t.get("account_id") in allowed]
        # Convert dates and datetimes to ISO strings, the same JSON the client receives.
        result = save_transactions(
            jsonable_encoder(transactions), start_date, end_date, item_id=item_id
        )
    except Exception as exc:
        return None, {**bank, "status": "error", "error": describe_sync_error(exc)}
    return result, {
        **bank,
        "status": "ok",
        "fetched": result["fetched"],
        "saved": result["inserted"] + result["updated"],
    }


def sync_all_banks(plaid_client, tokens, start_date, end_date):
    """Sync every connected bank. One bank failing does not stop the others.

    Returns (combined save_result, per-bank statuses). Raises only if every bank failed.
    """
    names = {item["item_id"]: item["institution_name"] for item in get_plaid_items()}
    combined = {key: 0 for key in SYNC_COUNT_KEYS}
    combined["total_in_database"] = 0
    banks = []
    for item_id, access_token in tokens.items():
        result, bank = sync_bank(
            plaid_client, item_id, access_token, names.get(item_id) or "Bank", start_date, end_date
        )
        banks.append(bank)
        if result is None:
            continue
        for key in SYNC_COUNT_KEYS:
            combined[key] += result[key]
        combined["total_in_database"] = result["total_in_database"]

    if banks and all(bank["status"] == "error" for bank in banks):
        details = "; ".join(f"{b['institution_name']}: {b['error']}" for b in banks)
        raise HTTPException(status_code=502, detail=f"Could not refresh any bank. {details}")
    return combined, banks


@app.post(
        "/get_transactions",
        summary="Get all transactions between a specified time period for the connected account",
        description="Retrieve all transactions between a specified time period for the connected account using the stored access token.",
        status_code=200,
)
def get_transactions(
    start_date: datetime.date,
    end_date: datetime.date,
    tokens: dict[str, str] = Depends(read_access_tokens),
    plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client),
):
    """Retrieve all transactions between a specified time period for every connected bank."""
    transactions = []
    for access_token in tokens.values():
        transactions.extend(fetch_all_transactions(plaid_client, access_token, start_date, end_date))
    return transactions


@app.post(
    "/api/save_transactions",
    summary="Fetch transactions and save them to the database",
    description="Retrieve all transactions between a specified time period for the connected account and store them in the SQLite database. Safe to run repeatedly: existing transactions are updated, not duplicated.",
    status_code=200,
)
def store_transactions(
    start_date: datetime.date,
    end_date: datetime.date,
    tokens: dict[str, str] = Depends(read_access_tokens),
    plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client),
):
    """Fetch transactions from every connected bank and save everything returned to the database."""
    combined, banks = sync_all_banks(plaid_client, tokens, start_date, end_date)
    return {**combined, "banks": banks}


# --- Monthly Income Endpoints ------------------------------------------------


@app.get(
    "/api/income",
    summary="Get stored monthly income",
    description="Retrieve the user's stored monthly income from the database.",
    status_code=200,
)
def fetch_income(month: str | None = None):
    return get_monthly_income(month)


@app.post(
    "/api/income",
    summary="Save monthly income",
    description="Store the user's monthly income in the database.",
    status_code=200,
)
async def update_income(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    income_val = data.get("income", 0.0)
    month_val = data.get("month")
    try:
        income_float = float(income_val)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid income value")
    if income_float < 0:
        raise HTTPException(status_code=400, detail="Income cannot be negative")

    return save_monthly_income(income_float, month_val)


# --- Category Rules Endpoints ------------------------------------------------


@app.get(
    "/api/category_rules",
    summary="Get classification rules",
    description="Retrieve the category rules for classifying transaction names.",
    status_code=200,
)
def fetch_category_rules():
    return load_category_rules()


@app.post(
    "/api/category_rules",
    summary="Save classification rules",
    description="Update the rules file used to classify transaction names into categories.",
    status_code=200,
)
async def update_category_rules(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    return save_category_rules(data)


@app.get(
    "/api/category_rules/export",
    summary="Export classification rules file",
    description="Download the category rules JSON file.",
    status_code=200,
)
def export_category_rules():
    path = get_rules_file_path()
    if not path.exists():
        load_category_rules()  # ensures file is created with defaults
    return FileResponse(
        path,
        media_type="application/json",
        filename="category_rules.json",
    )


@app.post(
    "/api/category_rules/import",
    summary="Import classification rules file",
    description="Upload and replace category rules from a JSON file or payload.",
    status_code=200,
)
async def import_category_rules(request: Request):
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if not uploaded:
            raise HTTPException(status_code=400, detail="No file uploaded")
        content = await uploaded.read()
        try:
            data = json.loads(content.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Uploaded file is not valid JSON")
    else:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return save_category_rules(data)


# --- Expenses Endpoints ------------------------------------------------------



@app.get(
    "/api/expenses",
    summary="Get classified expenses",
    description="Retrieve expenses from the database classified by category rules, with totals and exclusions.",
    status_code=200,
)
def fetch_expenses(month: str | None = None, expenses_only: bool = True):
    expenses, available_months = build_expense_rows(month, expenses_only)
    return summarize_expenses(expenses, available_months, month)


def build_expense_rows(month: str | None, expenses_only: bool):
    """Build the classified expense rows (bank + custom) shared by the expense endpoints."""
    rules = load_category_rules()
    exclusions = get_transaction_exclusions(month)
    transactions = get_saved_transactions(month=month, expenses_only=expenses_only)
    custom_txs = get_custom_expenses(month=month)
    available_months = get_transaction_months()

    expenses = []
    for tx in transactions:
        name = tx.get("name") or tx.get("merchant_name") or "Unnamed Transaction"
        category = classify_transaction(name, rules)
        tx_id = tx["transaction_id"]
        expenses.append({
            "transaction_id": tx_id,
            "name": name,
            "merchant_name": tx.get("merchant_name"),
            "institution_name": tx.get("institution_name"),
            "amount": tx["amount"],
            "amount_cents": tx.get("amount_cents"),
            "date": tx.get("date"),
            "category": category,
            "excluded": tx_id in exclusions,
            "is_custom": False,
            "is_recurring": False,
            "pfc_primary": tx.get("pfc_primary"),
            "pfc_detailed": tx.get("pfc_detailed"),
        })

    is_all_months = not month or month.lower() == "all"
    for cx in custom_txs:
        cx_id = cx["id"]
        cat = cx.get("category") or classify_transaction(cx["name"], rules)
        is_rec = bool(cx.get("is_recurring", False))

        if is_rec and is_all_months:
            # In All Months view, recurring expenses appear once per available month with each month's date
            months_to_gen = (
                available_months
                if available_months
                else [cx.get("date", "")[:7] or datetime.date.today().strftime("%Y-%m")]
            )
            for m in months_to_gen:
                cx_date = format_recurring_date(cx.get("date"), m)
                item_tx_id = f"{cx_id}::{m}"
                is_excl = (cx_id in exclusions and f"{cx_id}::{m}" in exclusions) or (item_tx_id in exclusions)
                expenses.append({
                    "transaction_id": item_tx_id,
                    "custom_id": cx_id,
                    "name": cx["name"],
                    "merchant_name": None,
                    "institution_name": None,
                    "amount": cx["amount"],
                    "amount_cents": int(round(cx["amount"] * 100)),
                    "date": cx_date,
                    "category": cat,
                    "excluded": is_excl,
                    "is_custom": True,
                    "is_recurring": True,
                    "pfc_primary": "CUSTOM",
                    "pfc_detailed": "CUSTOM_EXPENSE",
                })
        else:
            if is_rec and not is_all_months and month:
                cx_date = format_recurring_date(cx.get("date"), month)
            else:
                cx_date = cx.get("date")

            expenses.append({
                "transaction_id": cx_id,
                "custom_id": cx_id,
                "name": cx["name"],
                "merchant_name": None,
                "institution_name": None,
                "amount": cx["amount"],
                "amount_cents": int(round(cx["amount"] * 100)),
                "date": cx_date,
                "category": cat,
                "excluded": cx_id in exclusions,
                "is_custom": True,
                "is_recurring": is_rec,
                "pfc_primary": "CUSTOM",
                "pfc_detailed": "CUSTOM_EXPENSE",
            })

    # Sort newest date first, then by name
    expenses.sort(
        key=lambda item: (item.get("date") or "0000-00-00", item.get("name") or ""),
        reverse=True,
    )
    return expenses, available_months


def summarize_expenses(expenses, available_months, month: str | None):
    # Excluded transactions are omitted from total_expenses calculation
    total_expenses = sum(
        e["amount"] for e in expenses if not e["excluded"] and e["amount"] is not None
    )
    total_all = sum(e["amount"] for e in expenses if e["amount"] is not None)
    excluded_count = sum(1 for e in expenses if e["excluded"])

    income_data = get_monthly_income(month)
    income = income_data["income"]
    leftover = round(income - total_expenses, 2)

    return {
        "expenses": expenses,
        "total_expenses": round(total_expenses, 2),
        "total_all": round(total_all, 2),
        "income": income,
        "leftover": leftover,
        "count": len(expenses),
        "excluded_count": excluded_count,
        "month": month or "all",
        "available_months": available_months,
    }


PIE_OTHER_LABEL = "Other"


@app.get(
    "/api/expenses/category_summary",
    summary="Get expense totals grouped by category",
    description=(
        "Group the same rows the expenses table shows by category. Excluded rows are left out of "
        "the totals. Returns every category (for the totals table) and pie slices (positive totals "
        "only, with the smallest slices merged into 'Other')."
    ),
    status_code=200,
)
def fetch_category_summary(
    month: str | None = None,
    expenses_only: bool = True,
    search: str | None = None,
    category: str | None = None,
    max_slices: int = 7,
):
    rows, _ = build_expense_rows(month, expenses_only)

    # Same filters the expenses table applies in the browser.
    query = (search or "").strip().lower()
    wanted_category = (category or "").strip()
    filtered = []
    for e in rows:
        if query:
            name_hit = query in (e.get("name") or "").lower()
            merchant_hit = query in (e.get("merchant_name") or "").lower()
            if not (name_hit or merchant_hit):
                continue
        if wanted_category and wanted_category.upper() != "ALL" and e["category"] != wanted_category:
            continue
        filtered.append(e)

    excluded_count = sum(1 for e in filtered if e["excluded"])
    included = [e for e in filtered if not e["excluded"] and e["amount"] is not None]

    # Sum in integer cents so totals don't pick up floating point drift.
    groups: dict[str, dict] = {}
    for e in included:
        g = groups.setdefault(e["category"], {"count": 0, "cents": 0})
        g["count"] += 1
        g["cents"] += int(round(e["amount"] * 100))

    grand_cents = sum(g["cents"] for g in groups.values())

    def pct(part_cents: int, whole_cents: int) -> float:
        return round(part_cents / whole_cents * 100, 1) if whole_cents else 0.0

    ordered = sorted(groups.items(), key=lambda kv: (-kv[1]["cents"], kv[0]))
    categories = [
        {
            "category": name,
            "count": g["count"],
            "total": g["cents"] / 100,
            "share": pct(g["cents"], grand_cents),
        }
        for name, g in ordered
    ]

    # Pie: positive totals only (credits can't be a slice).
    positives = [(name, g) for name, g in ordered if g["cents"] > 0]
    positive_cents = sum(g["cents"] for _, g in positives)
    max_slices = max(1, max_slices)
    keep, rest = positives[:max_slices], positives[max_slices:]
    # Merging a single leftover into "Other" would only hide its name.
    if len(rest) == 1:
        keep, rest = positives, []

    pie = [
        {
            "category": name,
            "total": g["cents"] / 100,
            "count": g["count"],
            "share": pct(g["cents"], positive_cents),
            "is_other": False,
            "merged_categories": 0,
        }
        for name, g in keep
    ]
    if rest:
        other_cents = sum(g["cents"] for _, g in rest)
        pie.append(
            {
                "category": PIE_OTHER_LABEL,
                "total": other_cents / 100,
                "count": sum(g["count"] for _, g in rest),
                "share": pct(other_cents, positive_cents),
                "is_other": True,
                "merged_categories": len(rest),
            }
        )

    return {
        "month": month or "all",
        "categories": categories,
        "pie": pie,
        "total": grand_cents / 100,
        "positive_total": positive_cents / 100,
        "count": len(included),
        "excluded_count": excluded_count,
    }


@app.post(
    "/api/expenses/toggle_exclusion",
    summary="Toggle transaction exclusion for a month",
    description="Autosave whether a transaction is excluded from a month's calculations.",
    status_code=200,
)
async def toggle_exclusion(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    transaction_id = data.get("transaction_id")
    month = data.get("month")
    excluded = bool(data.get("excluded", True))
    if not transaction_id:
        raise HTTPException(status_code=400, detail="transaction_id is required")

    # If the transaction_id was scoped as custom_id::month (e.g. from All Months view)
    if "::" in transaction_id:
        real_tx_id, scoped_month = transaction_id.split("::", 1)
        target_month = scoped_month if (not month or month.lower() == "all") else month
        set_transaction_exclusion(real_tx_id, target_month, excluded)
        return {
            "status": "saved",
            "transaction_id": transaction_id,
            "month": target_month,
            "excluded": excluded,
        }

    set_transaction_exclusion(transaction_id, month, excluded)
    return {
        "status": "saved",
        "transaction_id": transaction_id,
        "month": month,
        "excluded": excluded,
    }



@app.post(
    "/api/custom_expenses",
    summary="Add custom expense",
    description="Add a manual custom expense, optionally recurring each month.",
    status_code=200,
)
async def create_custom_expense(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    name = data.get("name")
    if not name or not str(name).strip():
        raise HTTPException(status_code=400, detail="Expense name is required")
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid amount")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    category = data.get("category")
    date_str = data.get("date")
    month = data.get("month")
    is_recurring = bool(data.get("is_recurring", False))

    item = add_custom_expense(
        name=name,
        amount=amount,
        category=category,
        date_str=date_str,
        month=month,
        is_recurring=is_recurring,
    )
    return item


@app.delete(
    "/api/custom_expenses/{custom_id}",
    summary="Delete custom expense",
    description="Delete a custom expense by its ID.",
    status_code=200,
)
def remove_custom_expense(custom_id: str):
    deleted = delete_custom_expense(custom_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom expense not found")
    return {"status": "deleted", "id": custom_id}


@app.put(
    "/api/custom_expenses/{custom_id}",
    summary="Update custom expense",
    description="Update a custom expense by its ID.",
    status_code=200,
)
async def edit_custom_expense(custom_id: str, request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    updated = update_custom_expense(
        custom_id=custom_id,
        name=data.get("name"),
        amount=float(data["amount"]) if "amount" in data else None,
        category=data.get("category"),
        date_str=data.get("date"),
        is_recurring=bool(data["is_recurring"]) if "is_recurring" in data else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Custom expense not found")
    return updated


@app.post(
    "/api/refresh_transactions",
    summary="Refresh past 3 months transactions",
    description="Fetch transactions for the past 3 months from Plaid and save them to the database.",
    status_code=200,
)
def refresh_past_3_months(
    tokens: dict[str, str] = Depends(read_access_tokens),
    plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client),
):
    # 90 days covers the past 3 months
    start_date, end_date = default_sync_window()

    save_result, banks = sync_all_banks(plaid_client, tokens, start_date, end_date)
    return {
        "status": "success" if all(bank["status"] == "ok" for bank in banks) else "partial",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "save_result": save_result,
        "banks": banks,
    }






def format_error(error):
    """Convert a Plaid exception into a JSON error payload."""
    try:
        response = json.loads(error.body)
    except (json.JSONDecodeError, TypeError):
        response = {"error_message": str(error)}
    return {**response, "status_code": error.status}


@app.exception_handler(plaid.ApiException)
async def handle_plaid_error(request: Request, error):
    """Return consistent JSON responses for Plaid API failures."""
    return JSONResponse(
        content={"error": format_error(error)},
        status_code=error.status,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))