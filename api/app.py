import plaid
from plaid.api import plaid_api

if __package__:
    from .auth import get_plaid_credentials
else:
    from auth import get_plaid_credentials

def get_plaid_client():
    client_id, secret = get_plaid_credentials()

    # Configure the Plaid SDK
    configuration = plaid.Configuration(
        host=plaid.Environment.Production,
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