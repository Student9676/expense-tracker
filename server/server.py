import json
import os

import plaid
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from credentials import get_plaid_credentials, save_key

load_dotenv()

app = FastAPI(
    title="Expense Tracker Plaid Server",
    description="HTTP server for Plaid authentication and setup operations.",
)

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
_plaid_client = None


def get_plaid_host():
    """Return the Plaid host configured for the current environment."""
    if PLAID_ENV == "sandbox":
        return plaid.Environment.Sandbox
    if PLAID_ENV == "production":
        return plaid.Environment.Production
    raise ValueError("PLAID_ENV must be 'sandbox' or 'production'")


def get_plaid_client():
    """Create the shared Plaid client on the first explicit server operation."""
    global _plaid_client
    if _plaid_client is not None:
        return _plaid_client

    client_id, secret = get_plaid_credentials()
    configuration = plaid.Configuration(
        host=get_plaid_host(),
        api_key={
            "clientId": client_id,
            "secret": secret,
            "plaidVersion": "2020-09-14",
        },
    )
    _plaid_client = plaid_api.PlaidApi(plaid.ApiClient(configuration))
    return _plaid_client


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


@app.post(
    "/api/initialize",
    summary="Initialize the Plaid client",
    description="Authenticate and initialize the shared Plaid client.",
    status_code=200,
)
def initialize_plaid_client():
    """Create the Plaid API client."""
    was_initialized = _plaid_client is not None
    get_plaid_client()
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
def create_link_token():
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

    response = get_plaid_client().link_token_create(link_request)
    return response.to_dict()


def save_plaid_access_token(access_token):
    """Save the Plaid access token in the keychain secrets manager."""
    service_name = os.getenv("PLAID_SERVICE_NAME")
    if not service_name:
        raise ValueError("PLAID_SERVICE_NAME is not configured in .env")

    save_key(
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
async def set_access_token(request: Request):
    """Exchange the public token with Plaid and securely save the access token."""

    form = await request.form()
    public_token = form.get("public_token")
    if not public_token:
        return JSONResponse(
            content={"error": "public_token is required"},
            status_code=400,
        )

    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = get_plaid_client().item_public_token_exchange(exchange_request)
    save_plaid_access_token(response["access_token"])
    return {
        "status": "connected",
        "item_id": response["item_id"],
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
