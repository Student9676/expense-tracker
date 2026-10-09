import os
import getpass
import json
from pathlib import Path
from dotenv import load_dotenv
import Security


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

SERVICE_NAME = os.getenv("PLAID_SERVICE_NAME")
CLIENT_ID = os.getenv("PLAID_CLIENT_ID")

if not SERVICE_NAME or not CLIENT_ID:
    raise ValueError("PLAID_SERVICE_NAME and PLAID_CLIENT_ID must be configured in .env")


def store_credentials(client_id, secret):
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: SERVICE_NAME,
        Security.kSecAttrAccount: "plaid_credentials",
    }
    Security.SecItemDelete(query)
    attributes = {
        **query,
        Security.kSecValueData: json.dumps(
            {"client_id": client_id, "secret": secret}
        ).encode("utf-8"),
        Security.kSecAttrAccessible: Security.kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
    }
    status, _ = Security.SecItemAdd(attributes, None)
    if status != Security.errSecSuccess:
        raise RuntimeError(f"Unable to store Keychain item: {status}")


# Securely prompt for Plaid Secret
plaid_secret = getpass.getpass(prompt="Enter your Plaid Production Secret: ")

# Save both credentials in one macOS Keychain item.
store_credentials(CLIENT_ID, plaid_secret)

print("Plaid credentials securely stored in the macOS Keychain.")