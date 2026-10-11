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
    raise ValueError(
        "PLAID_SERVICE_NAME and PLAID_CLIENT_ID must be configured in .env"
    )


def normalize_environment(value):
    aliases = {
        "s": "sandbox",
        "sand": "sandbox",
        "sandbox": "sandbox",
        "d": "production",
        "dev": "production",
        "development": "production",
        "p": "production",
        "prod": "production",
        "production": "production",
    }
    try:
        return aliases[value.strip().lower()]
    except KeyError as error:
        raise ValueError(
            "Environment must be sandbox or production "
            "(aliases: s, sand, p, prod)"
        ) from error


PLAID_ENV = normalize_environment(
    input("Set secrets for Plaid sandbox or production? (s/p): ")
)
KEYCHAIN_ACCOUNT = f"plaid_credentials_{PLAID_ENV}"

env_path = BASE_DIR / ".env"
env_lines = env_path.read_text().splitlines() if env_path.exists() else []
for index, line in enumerate(env_lines):
    if line.startswith("PLAID_ENV="):
        env_lines[index] = f"PLAID_ENV={PLAID_ENV}"
        break
else:
    env_lines.append(f"PLAID_ENV={PLAID_ENV}")
env_path.write_text("\n".join(env_lines) + "\n")


def store_credentials(client_id, secret):
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: SERVICE_NAME,
        Security.kSecAttrAccount: KEYCHAIN_ACCOUNT,
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


# Securely prompt for the selected environment's Plaid secret.
plaid_secret = getpass.getpass(prompt=f"Enter your Plaid {PLAID_ENV} Secret: ")

# Save both credentials in one environment-specific macOS Keychain item.
store_credentials(CLIENT_ID, plaid_secret)

print("Plaid credentials securely stored in the macOS Keychain.")