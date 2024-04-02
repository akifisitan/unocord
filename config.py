import os
from dotenv import load_dotenv
from firebase_admin import db, credentials, initialize_app as firebase_init
import json

load_dotenv()

DEV = os.environ.get("PY_ENV") != "PROD"

BOT_TOKEN = os.environ.get("BOT_TOKEN" if not DEV else "BOT_TOKEN_DEV")

SERVER_IDS = [
    int(server_id)
    for server_id in os.environ.get("SERVER_IDS").split(",")
    if server_id.isdigit()
]

FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDS")
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL")

firebase_init(
    credentials.Certificate(json.loads(FIREBASE_CREDENTIALS)),
    {"databaseURL": FIREBASE_DB_URL},
)

FIREBASE_DB_NAME = os.environ.get(
    "FIREBASE_DB_NAME" if not DEV else "FIREBASE_DB_NAME_DEV"
)
firebase_database = db.reference(f"/{FIREBASE_DB_NAME}")
