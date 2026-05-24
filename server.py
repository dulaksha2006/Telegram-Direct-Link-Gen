"""
FastAPI streaming server — Telethon GetFileRequest backend.
"""
import logging
import mimetypes
import re
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

import config
import sheets
from stream_worker import get_file_info, stream_file, get_client

log = logging.getLogger(__name__)
app = FastAPI(title="TG Direct Downloader", docs_url=None, redoc_url=None)

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _mime(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    return mt or "application/octet-stream"


def _parse_range(header: str, file_size: int):
    if not header or not file_size:
        return 0, file_size - 1, 200
    m = RANGE_RE.search(header)
    if not m:
        return 0, file_size - 1, 200
    s, e = m.group(1), m.group(2)
    from_b  = int(s) if s else 0
    until_b = int(e) if e else file_size - 1
    until_b = min(until_b, file_size - 1)
    if from_b > until_b:
        return 0, file_size - 1, 200
    return from_b, until_b, 206


@app.get("/", response_class=HTMLResponse)
async def home():
    return """<!DOCTYPE html><html lang="si"><head><meta charset="UTF-8">
<title>TG Direct Downloader</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:sans-serif;background:#0a0f1e;min-height:100vh;
     display:flex;align-items:center;justify-content:center;color:#e2e8f0}
.wrap{max-width:440px;width:90%;text-align:center}
h1{font-size:28px;margin-bottom:12px;color:#60a5fa}
p{color:#94a3b8;margin-bottom:20px}
.dot{display:inline-block;width:8px;height:8px;background:#22c55e;
     border-radius:50%;margin-right:6px}
</style></head><body>
<div class="wrap">
  <h1>📡 TG Direct Downloader</h1>
  <p>Telegram files → direct streaming links<br>Up to 4 GB · Restart-safe via Google Sheets</p>
  <p><span class="dot"></span>Online</p>
</div></body></html>"""


@app.get("/download/{uid}/{filename}")
async def download(uid: str, filename: str, request: Request):
    info = await sheets.aget(uid)
    if not info:
        raise HTTPException(404, "File not found. Bot restart වෙලා ඇති – නැවත file send කරන්න.")

    display = unquote(filename)
    size    = info.get("file_size", 0)

    range_hdr             = request.headers.get("Range", "")
    from_b, until_b, status = _parse_range(range_hdr, size)
    content_length        = until_b - from_b + 1 if size else 0

    mime = info.get("mime_type") or _mime(display)

    headers = {
        "Content-Disposition": f'attachment; filename="{display}"',
        "Accept-Ranges":       "bytes",
        "Content-Type":        mime,
    }
    if size:
        headers["Content-Length"] = str(content_length)
    if status == 206:
        headers["Content-Range"] = f"bytes {from_b}-{until_b}/{size}"

    # ── Source selection ──────────────────────────────────────────
    channel_msg_id = info.get("channel_msg_id")
    orig_chat_id   = info.get("chat_id")
    orig_msg_id    = info.get("message_id")

    # Primary: storage channel. Fallback: original chat.
    if channel_msg_id:
        primary_chat = config.STORAGE_CHANNEL
        primary_msg  = channel_msg_id
        fallback_chat = orig_chat_id
        fallback_msg  = orig_msg_id
    else:
        primary_chat  = orig_chat_id
        primary_msg   = orig_msg_id
        fallback_chat = None
        fallback_msg  = None

    if not primary_chat or not primary_msg:
        raise HTTPException(500, "Stream source not available.")

    try:
        primary_chat  = int(primary_chat)
        primary_msg   = int(primary_msg)
        fallback_chat = int(fallback_chat) if fallback_chat else None
        fallback_msg  = int(fallback_msg)  if fallback_msg  else None
    except (TypeError, ValueError) as e:
        log.error(f"Invalid source ids for uid={uid}: {e}")
        raise HTTPException(500, "Invalid stream source data.")

    # ── Fetch file info (with fallback) ───────────────────────────
    file_info = await get_file_info(
        primary_chat, primary_msg,
        fallback_chat_id=fallback_chat,
        fallback_message_id=fallback_msg,
    )

    if not file_info:
        log.error(
            f"File not accessible. uid={uid} "
            f"primary=({primary_chat},{primary_msg}) "
            f"fallback=({fallback_chat},{fallback_msg}) "
            f"cache_info={info}"
        )
        raise HTTPException(
            404,
            f"File not accessible. Bot storage channel ({config.STORAGE_CHANNEL}) "
            f"හි bot admin ද? Channel id නිවැරදිද? Logs check කරන්න."
        )

    # ── Use actual file size if sheets had 0 ──────────────────────
    if not size and file_info.file_size:
        size                     = file_info.file_size
        from_b, until_b, status  = _parse_range(range_hdr, size)
        content_length           = until_b - from_b + 1
        headers["Content-Length"] = str(content_length)

    async def generator():
        try:
            async for chunk in stream_file(file_info, from_b, until_b):
                yield chunk
        except Exception as e:
            log.error(f"Stream error uid={uid}: {e}", exc_info=True)

    return StreamingResponse(
        generator(),
        status_code=status,
        media_type=mime,
        headers=headers,
    )


@app.get("/health")
async def health():
    try:
        connected = get_client().is_connected()
    except Exception:
        connected = False
    return {
        "status":      "ok",
        "telethon":    connected,
        "cache_files": len(sheets._cache),
    }
