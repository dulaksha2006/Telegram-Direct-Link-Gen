"""
FastAPI streaming server.
  GET /download/{uid}/{filename}  – stream file
  GET /health                     – health check

Restart-safe: file info Google Sheet එකෙන් load කරනවා.
Stream logic: FileToLink pattern (chunk_offset/chunk_limit) use කරනවා.
"""
import logging
import mimetypes
import re
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

import config
import sheets
from pyro_client import stream_file, get_client

logger = logging.getLogger(__name__)
app = FastAPI(title="TG Direct Downloader", docs_url=None, redoc_url=None)

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _mime(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    return mt or "application/octet-stream"


def _parse_range(range_header: str, file_size: int):
    """Returns (start, end, status_code)"""
    if not range_header or not file_size:
        return 0, file_size - 1 if file_size else 0, 200

    m = RANGE_RE.fullmatch(range_header.strip())
    if not m:
        return 0, file_size - 1, 200

    start_s, end_s = m.group(1), m.group(2)
    if start_s:
        start = int(start_s)
        end   = int(end_s) if end_s else file_size - 1
    else:
        # suffix range
        suffix = int(end_s) if end_s else 0
        start  = max(file_size - suffix, 0)
        end    = file_size - 1

    if start > end or end >= file_size:
        return 0, file_size - 1, 200

    return start, end, 206


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
  .icon{font-size:72px;margin-bottom:28px;display:block;animation:float 3s ease-in-out infinite}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
  h1{font-size:32px;font-weight:700;
     background:linear-gradient(135deg,#60a5fa,#a78bfa);
     -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px}
  p{color:#94a3b8;line-height:1.7;margin-bottom:32px}
  .badge{display:inline-block;background:rgba(96,165,250,.12);
         border:1px solid rgba(96,165,250,.3);border-radius:8px;
         padding:6px 14px;font-size:13px;color:#60a5fa;margin:4px}
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
     Bot API (20 MB) + MTProto (4 GB) + Restart-safe Google Sheet backup.</p>
  <div>
    <span class="badge">⚡ Up to 4 GB</span>
    <span class="badge">🔗 Direct links</span>
    <span class="badge">📶 Streaming</span>
    <span class="badge">💾 Restart-safe</span>
  </div>
  <div class="status"><span class="dot"></span>Server Online</div>
</div>
</body>
</html>"""


@app.get("/download/{uid}/{filename}")
async def download(uid: str, filename: str, request: Request):
    info = sheets.get(uid)
    if not info:
        raise HTTPException(
            404,
            "File not found. Bot restart වෙලා ඇති – නැවත file send කරන්න."
        )

    display = unquote(filename)
    mime    = _mime(display)
    size    = info.get("file_size", 0)

    range_header        = request.headers.get("Range", "")
    start, end, status  = _parse_range(range_header, size)
    content_length      = end - start + 1 if size else 0

    headers = {
        "Content-Disposition": f'attachment; filename="{display}"',
        "Accept-Ranges":       "bytes",
        "Content-Type":        mime,
    }
    if size:
        headers["Content-Length"] = str(content_length)
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    # ── Streaming source selection ────────────────────────────────
    # Priority:
    #   1. STORAGE_CHANNEL forwarded msg  (Pyrogram, restart-safe)
    #   2. Original chat+msg              (Pyrogram, session-only)
    #   3. Bot API file_id                (≤20 MB only)

    channel_msg_id = info.get("channel_msg_id")
    chat_id        = info.get("chat_id")
    message_id     = info.get("message_id")

    use_pyrogram = info.get("big") or (channel_msg_id is not None)
    pyro_chat    = config.STORAGE_CHANNEL if channel_msg_id else chat_id
    pyro_msg     = channel_msg_id if channel_msg_id else message_id

    if use_pyrogram and pyro_chat and pyro_msg:
        async def pyro_gen():
            try:
                async for chunk in stream_file(
                    chat_id=pyro_chat,
                    message_id=pyro_msg,
                    offset=start,
                    limit=content_length,
                ):
                    yield chunk
            except Exception as e:
                logger.error(f"Pyrogram stream error: {e}", exc_info=True)

        return StreamingResponse(
            pyro_gen(), status_code=status, media_type=mime, headers=headers
        )

    else:
        # Bot API path (≤20 MB, no Pyrogram session or not big)
        from telegram import Bot
        bot     = Bot(token=config.BOT_TOKEN)
        tg_file = await bot.get_file(info["file_id"])
        url     = tg_file.file_path

        async def bot_gen():
            req_headers = {}
            if range_header:
                req_headers["Range"] = range_header
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("GET", url, headers=req_headers) as r:
                    async for chunk in r.aiter_bytes(65536):
                        yield chunk

        return StreamingResponse(
            bot_gen(), status_code=status, media_type=mime, headers=headers
        )


@app.get("/health")
async def health():
    try:
        c = get_client()
        connected = c.is_connected
    except Exception:
        connected = False
    cache_size = len(sheets._cache)
    return {
        "status":      "ok",
        "pyrogram":    connected,
        "cache_files": cache_size,
    }
