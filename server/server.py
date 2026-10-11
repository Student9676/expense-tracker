import json
import os
import datetime

import plaid
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File
from contextlib import asynccontextmanager
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from credentials import get_api_credentials, save_access_token, get_access_token
from database import (
    init_database,
    save_transactions,
    get_monthly_income,
    save_monthly_income,
    get_saved_transactions,
    get_transaction_months,
)
from server.classifier import (
    classify_transaction,
    load_category_rules,
    save_category_rules,
    get_rules_file_path,
)

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Retrieve the access token once during server startup
    try:
        token = get_access_token(PLAID_SERVICE_NAME, PLAID_ENV)
        app.state.access_token = token
    except Exception as e:
        # Handle keychain access errors gracefully
        print(f"Keychain access failed: {e}")
        app.state.access_token = None

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

    yield  # Server starts running

    # Clear the token and client from memory on shutdown
    app.state.access_token = None
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


def read_access_token() -> str:
    token = getattr(app.state, "access_token", None)
    if not token:
        raise HTTPException(
            status_code=500,
            detail="Access token is missing or could not be retrieved from the Keychain."
        )
    return token


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
    return {
        "connected": bool(getattr(app.state, "access_token", None)),
    }


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


def save_plaid_access_token(access_token):
    """Save the Plaid access token in the keychain secrets manager."""
    service_name = os.getenv("PLAID_SERVICE_NAME")
    if not service_name:
        raise ValueError("PLAID_SERVICE_NAME is not configured in .env")

    save_access_token(
        "access_token",
        access_token,
        service_name,
        account=f"plaid_access_token_{PLAID_ENV}",
    )


# The client sends the public token after Plaid Link completes.
@app.post(
    "/api/set_access_token",
    summary="Exchange a Plaid public token",
    description="Exchange the Link public token and securely save the access token.",
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
    save_plaid_access_token(response["access_token"])
    app.state.access_token = response["access_token"]
    return {
        "status": "connected",
        "item_id": response["item_id"],
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


@app.post(
        "/get_transactions",
        summary="Get all transactions between a specified time period for the connected account",
        description="Retrieve all transactions between a specified time period for the connected account using the stored access token.",
        status_code=200,
)
def get_transactions(
    start_date: datetime.date,
    end_date: datetime.date,
    access_token: str = Depends(read_access_token),
    plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client),
):
    """Retrieve all transactions between a specified time period for the connected account using the stored access token."""
    return fetch_all_transactions(plaid_client, access_token, start_date, end_date)


@app.post(
    "/api/save_transactions",
    summary="Fetch transactions and save them to the database",
    description="Retrieve all transactions between a specified time period for the connected account and store them in the SQLite database. Safe to run repeatedly: existing transactions are updated, not duplicated.",
    status_code=200,
)
def store_transactions(
    start_date: datetime.date,
    end_date: datetime.date,
    access_token: str = Depends(read_access_token),
    plaid_client: plaid_api.PlaidApi = Depends(read_plaid_client),
):
    """Fetch transactions from Plaid and save everything returned to the database."""
    transactions = fetch_all_transactions(plaid_client, access_token, start_date, end_date)
    # Convert dates and datetimes to ISO strings, the same JSON the client receives.
    return save_transactions(jsonable_encoder(transactions), start_date, end_date)


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
    description="Retrieve expenses from the database classified by category rules, with totals.",
    status_code=200,
)
def fetch_expenses(month: str | None = None, expenses_only: bool = True):
    rules = load_category_rules()
    transactions = get_saved_transactions(month=month, expenses_only=expenses_only)
    expenses = []
    for tx in transactions:
        name = tx.get("name") or tx.get("merchant_name") or "Unnamed Transaction"
        category = classify_transaction(name, rules)
        expenses.append({
            "transaction_id": tx["transaction_id"],
            "name": name,
            "merchant_name": tx.get("merchant_name"),
            "amount": tx["amount"],
            "amount_cents": tx.get("amount_cents"),
            "date": tx.get("date"),
            "category": category,
            "pfc_primary": tx.get("pfc_primary"),
            "pfc_detailed": tx.get("pfc_detailed"),
        })

    total = sum(e["amount"] for e in expenses if e["amount"] is not None)
    available_months = get_transaction_months()
    income_data = get_monthly_income(month)
    income = income_data["income"]
    leftover = round(income - total, 2)

    return {
        "expenses": expenses,
        "total_expenses": round(total, 2),
        "income": income,
        "leftover": leftover,
        "count": len(expenses),
        "month": month or "all",
        "available_months": available_months,
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