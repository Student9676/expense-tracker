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


def _get_keychain_credentials(service_name, context):
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service_name,
        Security.kSecAttrAccount: "plaid_credentials",
        Security.kSecReturnData: True,
        Security.kSecUseAuthenticationContext: context,
    }
    status, data = Security.SecItemCopyMatching(query, None)
    if status != Security.errSecSuccess:
        return None, None
    credentials = json.loads(bytes(data).decode("utf-8"))
    return credentials.get("client_id"), credentials.get("secret")


def get_plaid_credentials():
    """Authenticate with Touch ID and return the stored Plaid credentials."""
    service_name = os.getenv("PLAID_SERVICE_NAME")
    if not service_name:
        raise ValueError("PLAID_SERVICE_NAME is not configured in .env")

    print("Requesting biometric authorization...")
    context = LAContext.new()
    if not authenticate_with_touch_id("access your Plaid credentials", context):
        raise PermissionError("Touch ID authentication failed")

    print("Touch ID verified. Fetching secure credentials...")
    client_id, secret = _get_keychain_credentials(service_name, context)

    if not client_id or not secret:
        raise ValueError("Plaid credentials not found! Run setup_secrets.py first.")

    print("Successfully retrieved Plaid credentials from the macOS Keychain.")
    return client_id, secret