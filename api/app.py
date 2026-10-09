import os

import plaid
from plaid.api import plaid_api

if __package__:
    from .auth import get_plaid_credentials
else:
    from auth import get_plaid_credentials

def get_plaid_client():
    client_id, secret = get_plaid_credentials()
    plaid_env = os.getenv("PLAID_ENV", "production").strip().lower()

    if plaid_env == "sandbox":
        host = plaid.Environment.Sandbox
    elif plaid_env == "production":
        host = plaid.Environment.Production
    else:
        raise ValueError("PLAID_ENV must be 'sandbox' or 'production'")

    # Configure the Plaid SDK
    configuration = plaid.Configuration(
        host=host,
        api_key={
            'clientId': client_id,
            'secret': secret,
        }
    )

    # Initialize and return the API client
    api_client = plaid.ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

    return client

if __name__ == "__main__":
    client = get_plaid_client()
    print("Successfully initialized Plaid Client.")