"""
FastAPI server
  GET /                         – landing page
  GET /download/{uid}/{name}    – stream file (Bot API < 20 MB, Pyrogram ≥ 20 MB)
  GET /health                   – health check
"""
import logging
import mimetypes
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response

import store
import config
from pyro_client import stream_file, get_client

logger = logging.getLogger(__name__)
app = FastAPI(title="TG Direct Downloader", docs_url=None, redoc_url=None)


# ── MIME helper ────────────────────────────────────────────────────

def _mime(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    return mt or "application/octet-stream"


# ── Landing page ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    return """<!DOCTYPE html>
<html lang="si">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TG Direct Downloader</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap');
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Space Grotesk',sans-serif;
       background:radial-gradient(ellipse at 20% 50%,#0d1b2a 0%,#0a0f1e 60%,#060912 100%);
       min-height:100vh;display:flex;align-items:center;justify-content:center;color:#e2e8f0}
  .wrap{max-width:480px;width:90%;text-align:center}
  .icon{font-size:72px;margin-bottom:28px;display:block;
        animation:float 3s ease-in-out infinite}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
  h1{font-size:32px;font-weight:700;
     background:linear-gradient(135deg,#60a5fa,#a78bfa);
     -webkit-background-clip:text;-webkit-text-fill-color:transparent;
     margin-bottom:12px}
  p{color:#94a3b8;line-height:1.7;margin-bottom:32px}
  .badge{display:inline-block;background:rgba(96,165,250,.12);
         border:1px solid rgba(96,165,250,.3);border-radius:8px;
         padding:6px 14px;font-size:13px;color:#60a5fa;margin:4px}
  .btn{display:inline-block;margin-top:28px;
       background:linear-gradient(135deg,#3b82f6,#8b5cf6);
       color:#fff;padding:14px 36px;border-radius:50px;
       text-decoration:none;font-weight:600;font-size:16px;
       box-shadow:0 8px 32px rgba(59,130,246,.35);
       transition:transform .2s,box-shadow .2s}
  .btn:hover{transform:translateY(-3px);box-shadow:0 12px 40px rgba(59,130,246,.5)}
  .status{margin-top:24px;font-size:13px;color:#475569}
  .dot{display:inline-block;width:8px;height:8px;background:#22c55e;
       border-radius:50%;margin-right:6px;animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>
<div class="wrap">
  <span class="icon">📡</span>
  <h1>TG Direct Downloader</h1>
  <p>Telegram files instant direct-link ලබා ගන්න.<br>
     Bot API (20 MB) + MTProto (4 GB) දෙකම support.</p>
  <div>
    <span class="badge">⚡ Up to 4 GB</span>
    <span class="badge">🔗 Direct links</span>
    <span class="badge">📶 Streaming</span>
    <span class="badge">⏩ Range requests</span>
  </div>
  <a class="btn" href="https://t.me/YourBotUsername">🤖 Bot Open කරන්න</a>
  <div class="status"><span class="dot"></span>Server Online</div>
</div>
</body>
</html>"""


# ── Download endpoint ──────────────────────────────────────────────

@app.get("/download/{uid}/{filename}")
async def download(uid: str, filename: str, request: Request):
    info = store.get(uid)
    if not info:
        raise HTTPException(404, "File not found – bot restart වෙලා ඇති. නැවත send කරන්න.")

    display = unquote(filename)
    mime    = _mime(display)
    size    = info.get("file_size", 0)

    headers_base = {
        "Content-Disposition": f'attachment; filename="{display}"',
        "Accept-Ranges": "bytes",
    }
    if size:
        headers_base["Content-Length"] = str(size)

    # ── Range header parsing (for video seekers / download managers) ──
    range_header = request.headers.get("Range")
    offset = 0
    status = 200

    if range_header and size:
        try:
            rng   = range_header.strip().replace("bytes=", "")
            start, end = rng.split("-")
            offset = int(start)
            end_b  = int(end) if end else size - 1
            length = end_b - offset + 1
            headers_base["Content-Range"]  = f"bytes {offset}-{end_b}/{size}"
            headers_base["Content-Length"] = str(length)
            status = 206
        except Exception:
            pass

    # ── Choose streaming method ────────────────────────────────────
    if info.get("big") and info.get("chat_id") and info.get("message_id"):
        # MTProto path (Pyrogram) — no size limit
        async def pyro_gen():
            async for chunk in stream_file(
                info["chat_id"], info["message_id"], offset=offset
            ):
                yield chunk

        return StreamingResponse(pyro_gen(), status_code=status,
                                  media_type=mime, headers=headers_base)
    else:
        # Bot API path — ≤ 20 MB
        from telegram import Bot
        bot = Bot(token=config.BOT_TOKEN)
        tg_file = await bot.get_file(info["file_id"])
        url     = tg_file.file_path

        async def bot_gen():
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("GET", url) as r:
                    async for chunk in r.aiter_bytes(65536):
                        yield chunk

        return StreamingResponse(bot_gen(), status_code=status,
                                  media_type=mime, headers=headers_base)


# ── Health ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        c = get_client()
        connected = c.is_connected
    except Exception:
        connected = False
    return {"status": "ok", "pyrogram": connected}
