import os
import getpass
from pathlib import Path
from dotenv import load_dotenv
import keyring


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

service_name = os.getenv("PLAID_SERVICE_NAME")
client_id = os.getenv("PLAID_CLIENT_ID")

keyring.set_password(service_name, "client_id", client_id)

# Securely prompt for Plaid Secret
plaid_secret = getpass.getpass(prompt="Enter your Plaid Secret: ")

# Save the secret to the OS Keyring
keyring.set_password(service_name, "secret", plaid_secret)

print("Plaid credentials securely stored in OS Keyring.")