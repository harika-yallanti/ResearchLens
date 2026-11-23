
import firebase_admin
from firebase_admin import credentials, auth
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SERVICE_ACCOUNT_PATH = (
    BASE_DIR / "credentials" / "firebase-service-account.json"
)

if not firebase_admin._apps:
    credential = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
    firebase_admin.initialize_app(credential)


def verify_firebase_token(id_token: str):
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print("Firebase token verification failed:", e)
        return None
