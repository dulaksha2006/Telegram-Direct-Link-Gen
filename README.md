# TG Direct Downloader — Restart-Safe Edition

## Files
| File | Description |
|---|---|
| `main.py` | Entry point |
| `bot.py` | Telegram bot handlers |
| `server.py` | FastAPI streaming server |
| `pyro_client.py` | Pyrogram MTProto client |
| `sheets.py` | Google Sheets store (Apps Script) |
| `config.py` | Environment variables |
| `appsscript_code.gs` | Google Apps Script code |

---

## Google Apps Script Setup (1 වතාවක් කරන්න)

1. **Google Sheet** create කරන්න (නමක් දෙන්න, e.g. "TG Bot Files")
2. **Extensions → Apps Script** click කරන්න
3. `appsscript_code.gs` file එකේ code **paste** කරන්න (default code delete කරලා)
4. **Save** (Ctrl+S)
5. **Deploy → New deployment**
   - Type: **Web app**
   - Execute as: **Me**
   - Who has access: **Anyone**
   - Click **Deploy**
6. **Web App URL copy** කරන්න → `SHEETS_WEBHOOK_URL` env var

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | BotFather token |
| `API_ID` | ✅ | my.telegram.org |
| `API_HASH` | ✅ | my.telegram.org |
| `SESSION_STR` | ✅ | Pyrogram string session |
| `BASE_URL` | ✅ | Server URL (e.g. https://your-app.up.railway.app) |
| `SHEETS_WEBHOOK_URL` | ✅ | Apps Script Web App URL |
| `STORAGE_CHANNEL` | ✅ | Channel ID (default: -1003978357179) |
| `PORT` | ❌ | Server port (default: 8000) |

---

## SESSION_STR Generate

```python
from pyrogram import Client
app = Client("s", api_id=API_ID, api_hash="API_HASH")
app.run(app.export_session_string())
```

---

## How It Works

```
File received
  → Forward to STORAGE_CHANNEL (permanent Telegram storage)
  → Save to Google Sheet via Apps Script URL
  → Reply with direct download link

Bot restart
  → Apps Script getAll → load all rows to memory cache
  → All links work immediately ✅

Download request
  → Read from memory cache
  → Stream from STORAGE_CHANNEL via Pyrogram
```
