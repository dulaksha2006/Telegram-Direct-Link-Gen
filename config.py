import os

# ── Telegram Bot API ──────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]

# ── Telegram MTProto (my.telegram.org) ──────────────────────────
API_ID      = int(os.environ["API_ID"])
API_HASH    = os.environ["API_HASH"]
SESSION_STR = os.environ.get("SESSION_STR", "")

# ── Web ──────────────────────────────────────────────────────────
BASE_URL    = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
PORT        = int(os.environ.get("PORT", 8000))

# ── Storage channel (files forward කරන channel) ─────────────────
STORAGE_CHANNEL = int(os.environ.get("STORAGE_CHANNEL", "-1003978357179"))

# ── Google Sheets via Apps Script Web App ───────────────────────
# appsscript_code.gs deploy කළාම ලැබෙන URL
SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL", "")

# ── Limits ───────────────────────────────────────────────────────
BOT_API_LIMIT = 20 * 1024 * 1024
