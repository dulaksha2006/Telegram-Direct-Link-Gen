import os

BOT_TOKEN        = os.environ["BOT_TOKEN"]
API_ID           = int(os.environ["API_ID"])
API_HASH         = os.environ["API_HASH"]
BASE_URL         = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
PORT             = int(os.environ.get("PORT", 8000))
STORAGE_CHANNEL  = int(os.environ.get("STORAGE_CHANNEL", "-1003978357179"))
SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL", "")
BOT_API_LIMIT    = 20 * 1024 * 1024
