# 📡 TG Direct Downloader — MTProto Edition

Telegram files **4 GB දක්වා** direct download link ලෙස stream කිරීමට Railway deploy කළ bot.

| Method | Limit | කවදා? |
|--------|-------|-------|
| Bot API | 20 MB | ≤ 20 MB files |
| **MTProto (Pyrogram)** | **4 GB** | **> 20 MB files** |

---

## 🗂️ File Structure

```
tg-dl-v2/
├── main.py              ← entry point
├── bot.py               ← Telegram bot handlers
├── server.py            ← FastAPI (download streaming)
├── pyro_client.py       ← Pyrogram MTProto client
├── store.py             ← in-memory file metadata store
├── config.py            ← env var loader
├── generate_session.py  ← SESSION_STR generator (run locally)
├── requirements.txt
├── railway.toml
├── Procfile
└── .gitignore
```

---

## 🚀 Deploy Steps

### Step 1 — Telegram Bot Token ගන්න

1. [@BotFather](https://t.me/BotFather) open කරන්න
2. `/newbot` → name + username දෙන්න
3. **BOT_TOKEN** copy කරගන්න

---

### Step 2 — API ID & API Hash ගන්න

1. [my.telegram.org](https://my.telegram.org) → Login (ඔබේ phone number)
2. **API Development Tools** → App හදන්න (name ඕනෑම දෙයක්)
3. `api_id` (number) සහ `api_hash` copy කරගන්න

---

### Step 3 — SESSION_STR Generate කරන්න *(local PC එකේ)*

```bash
# Python installed නැත්නම් install කරන්න
pip install pyrogram tgcrypto

# Project folder ඇතුළේ:
python generate_session.py
```

- Phone number enter කරන්න (+94xxxxxxxxx)
- OTP enter කරන්න
- 2FA password (තිබේ නම්)
- Terminal එකේ **SESSION_STR** print වෙනවා — copy කරගන්න

> ⚠️ SESSION_STR කාටවත් දෙන්න එපා. ඔබේ account access ලැබේ.

---

### Step 4 — GitHub Repo හදන්න

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_NAME/tg-dl-v2.git
git push -u origin main
```

---

### Step 5 — Railway Deploy

1. [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
2. Repo select කරන්න
3. **Variables** tab → Add:

| Variable | Value |
|----------|-------|
| `BOT_TOKEN` | BotFather token |
| `API_ID` | my.telegram.org api_id |
| `API_HASH` | my.telegram.org api_hash |
| `SESSION_STR` | generate කළ session string |
| `BASE_URL` | *(deploy පස්සේ add කරන්න)* |

4. Deploy → **Settings → Domains → Generate Domain**
5. ඒ URL copy කරලා `BASE_URL` variable දාන්න → **Redeploy**

---

### Step 6 — Test

- Bot open → `/start`
- ඕනෑම file send කරන්න (20 MB+ video ත් OK)
- Direct download link ලැබේ ✅

---

## 📋 Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram Bot token |
| `API_ID` | ✅ | Telegram API ID |
| `API_HASH` | ✅ | Telegram API Hash |
| `SESSION_STR` | ✅ | Pyrogram string session |
| `BASE_URL` | ✅ | Railway public URL |
| `PORT` | ❌ | Auto-set by Railway |

---

## 🔧 Troubleshooting

**Bot respond නොකරයි**
→ BOT_TOKEN හරිද check කරන්න

**20MB+ files fail වෙනවා**
→ SESSION_STR හරිද check කරන්න → `/health` endpoint check කරන්න

**"File not found" error**
→ Bot restart වෙලා ඇති (in-memory store clear වෙනවා)
→ File නැවත send කරන්න. (Redis add කළොත් persist වෙනවා)

**Railway deploy fail**
→ requirements.txt check කරන්න → Build logs බලන්න

---

## 🛡️ Security Notes

- `SESSION_STR` — ඔබේ Telegram account access. **GitHub push නොකරන්න.**
- Railway Variables encrypted ලෙස store වෙනවා.
- Bot හරහා share කරන links public — sensitive files share නොකරන්න.

---

## 📈 Upgrade Ideas

- **Redis** — file links persist කරන්න (restart survive)
- **Auth** — bot allowlist (specific users only)
- **Expiry links** — time-limited download URLs
- **Progress** — download progress bot message
