import os
import time
import json
from pathlib import Path

from dotenv import load_dotenv
from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthenticationWithBiometrics
import Security


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env")


def authenticate_with_touch_id(
    reason_string="authorize access to your secure application",
    context=None,
):
    """Return True when macOS Touch ID successfully authenticates the user."""
    if context is None:
        context = LAContext.new()
    can_evaluate, error = context.canEvaluatePolicy_error_(
        LAPolicyDeviceOwnerAuthenticationWithBiometrics,
        None,
    )

    if not can_evaluate:
        description = error.localizedDescription() if error else "Unknown error"
        print(f"Touch ID is unavailable: {description}")
        return False

    auth_success = False
    auth_finished = False

    def reply_handler(success, evaluation_error):
        nonlocal auth_success, auth_finished
        auth_success = success
        if not success and evaluation_error:
            print(f"Authentication failed: {evaluation_error.localizedDescription()}")
        auth_finished = True

    context.evaluatePolicy_localizedReason_reply_(
        LAPolicyDeviceOwnerAuthenticationWithBiometrics,
        reason_string,
        reply_handler,
    )

    while not auth_finished:
        time.sleep(0.1)

    return auth_success


def _get_keychain_credentials(service_name, plaid_env, context):
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service_name,
        Security.kSecAttrAccount: f"plaid_credentials_{plaid_env}",
        Security.kSecReturnData: True,
        Security.kSecUseAuthenticationContext: context,
    }
    status, data = Security.SecItemCopyMatching(query, None)
    if status != Security.errSecSuccess:
        return None, None
    credentials = json.loads(bytes(data).decode("utf-8"))
    return credentials.get("client_id"), credentials.get("secret")


def get_api_credentials():
    """Authenticate with Touch ID and return the stored Plaid credentials."""
    service_name = os.getenv("PLAID_SERVICE_NAME")
    plaid_env = os.getenv("PLAID_ENV", "production").strip().lower()
    if not service_name:
        raise ValueError("PLAID_SERVICE_NAME is not configured in .env")
    if plaid_env not in {"sandbox", "production"}:
        raise ValueError("PLAID_ENV must be 'sandbox' or 'production'")

    print(f"Requesting biometric authorization for Plaid {plaid_env}...")
    context = LAContext.new()
    if not authenticate_with_touch_id(
        f"access your Plaid {plaid_env} credentials", context
    ):
        raise PermissionError("Touch ID authentication failed")

    print(f"Touch ID verified. Fetching Plaid {plaid_env} credentials...")
    client_id, secret = _get_keychain_credentials(service_name, plaid_env, context)

    if not client_id or not secret:
        raise ValueError(
            f"Plaid {plaid_env} credentials not found! Run setup_secrets.py first."
        )

    print(
        f"Successfully retrieved Plaid {plaid_env} credentials "
        "from the macOS Keychain."
    )
    return client_id, secret


def save_access_token(key_name, key_value, service_name, account=None):
    """Save a generic-password value in the macOS Keychain."""
    if not key_name or not key_value or not service_name:
        raise ValueError("key_name, key_value, and service_name are required")

    account = account or key_name
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service_name,
        Security.kSecAttrAccount: account,
    }
    Security.SecItemDelete(query)
    attributes = {
        **query,
        Security.kSecValueData: str(key_value).encode("utf-8"),
        Security.kSecAttrAccessible: Security.kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
    }
    status, _ = Security.SecItemAdd(attributes, None)
    if status != Security.errSecSuccess:
        raise RuntimeError(f"Unable to store Keychain item: {status}")


def get_access_token(service_name, plaid_env):
    """Retrieve the saved Plaid access token from the macOS Keychain."""
    account = f"plaid_access_token_{plaid_env}"
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service_name,
        Security.kSecAttrAccount: account,
        Security.kSecReturnData: True,
    }
    status, data = Security.SecItemCopyMatching(query, None)
    if status != Security.errSecSuccess:
        return None
    return bytes(data).decode("utf-8")


def item_token_account(plaid_env, item_id):
    """Keychain account name for one bank's access token."""
    return f"plaid_access_token_{plaid_env}_{item_id}"


def get_item_access_token(service_name, plaid_env, item_id):
    """Retrieve the access token saved for one connected bank, or None if missing."""
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service_name,
        Security.kSecAttrAccount: item_token_account(plaid_env, item_id),
        Security.kSecReturnData: True,
    }
    status, data = Security.SecItemCopyMatching(query, None)
    if status != Security.errSecSuccess:
        return None
    return bytes(data).decode("utf-8")


def _delete_keychain_item(service_name, account):
    """Delete one generic-password item. A missing item counts as success."""
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service_name,
        Security.kSecAttrAccount: account,
    }
    status = Security.SecItemDelete(query)
    return status in (Security.errSecSuccess, Security.errSecItemNotFound)


def delete_bank_access_tokens(service_name, plaid_env, item_id, access_token=None):
    """Delete a bank's access token from the macOS Keychain.

    Also removes the single-token entry used before multi-bank support when it holds this
    same token. Otherwise the server would adopt it again at the next startup and the
    deleted bank would reappear.
    """
    if not service_name or not item_id:
        raise ValueError("service_name and item_id are required")

    if not _delete_keychain_item(service_name, item_token_account(plaid_env, item_id)):
        raise RuntimeError("Unable to delete the bank's Keychain item")

    legacy_token = get_access_token(service_name, plaid_env)
    if legacy_token and access_token and legacy_token == access_token:
        if not _delete_keychain_item(service_name, f"plaid_access_token_{plaid_env}"):
            raise RuntimeError("Unable to delete the legacy Keychain item")
