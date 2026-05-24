# TG Direct Downloader

## ⚡ Key change: Pyrogram → Telethon
Pyrogram's `stream_media()` has a known bug with range requests (0B downloads).
This version uses **Telethon + raw `GetFileRequest`** — same approach as the
proven TG-FileStreamBot project. Range requests, video seek, resume — all work.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | BotFather token |
| `API_ID` | ✅ | my.telegram.org |
| `API_HASH` | ✅ | my.telegram.org |
| `BASE_URL` | ✅ | Server URL (e.g. https://app.railway.app) |
| `STORAGE_CHANNEL` | ✅ | Channel ID (default: -1003978357179) |
| `SHEETS_WEBHOOK_URL` | ✅ | Apps Script Web App URL |
| `PORT` | ❌ | default 8000 |

**NOTE: SESSION_STR ඕනේ නෑ** — Bot token එකෙන්ම Telethon login වෙනවා.

## Google Apps Script Setup
1. Google Sheet create කරන්න
2. Extensions → Apps Script → `appsscript_code.gs` paste
3. Deploy → Web app → Execute as Me, Anyone access
4. URL copy → `SHEETS_WEBHOOK_URL`

## STORAGE_CHANNEL Setup
1. Telegram channel create (private)
2. **Bot admin** add කරන්න (post messages permission)
3. Channel ID → `STORAGE_CHANNEL`

## How It Works
```
File received → Bot forwards to STORAGE_CHANNEL → Save to Google Sheet
Bot restart   → Sheet load → memory cache restored → All links work ✅
Download      → Telethon GetFileRequest → Direct MTProto stream
```
