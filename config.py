import os

# ── Telegram Bot API ──────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]          # BotFather token

# ── Telegram MTProto (my.telegram.org) ──────────────────────────
API_ID      = int(os.environ["API_ID"])        # numeric
API_HASH    = os.environ["API_HASH"]
SESSION_STR = os.environ.get("SESSION_STR", "") # Pyrogram string session

# ── Web ──────────────────────────────────────────────────────────
BASE_URL    = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
PORT        = int(os.environ.get("PORT", 8000))

# ── Limits ───────────────────────────────────────────────────────
BOT_API_LIMIT = 20 * 1024 * 1024   # 20 MB  → use Bot API
# above this → use Pyrogram streaming (up to 4 GB)
