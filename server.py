"""
FastAPI streaming server — Telethon GetFileRequest backend.
Range requests, video seek, resume download සියල්ල work කරයි.
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
    """Returns (from_bytes, until_bytes, status)"""
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
    info = sheets.get(uid)
    if not info:
        raise HTTPException(404, "File not found. Bot restart වෙලා ඇති – නැවත file send කරන්න.")

    display = unquote(filename)
    size    = info.get("file_size", 0)

    # ── Range header ──────────────────────────────────────────────
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

    # ── Decide which message to stream from ──────────────────────
    # Prefer STORAGE_CHANNEL (persistent across restarts)
    channel_msg_id = info.get("channel_msg_id")
    chat_id        = config.STORAGE_CHANNEL if channel_msg_id else info.get("chat_id")
    message_id     = channel_msg_id if channel_msg_id else info.get("message_id")

    if not chat_id or not message_id:
        raise HTTPException(500, "Stream source not available.")

    # BUG FIX #3: chat_id must be int for Telethon — sheets.load() saves as int
    # but channel_msg_id path uses config.STORAGE_CHANNEL which is already int.
    # Extra guard: cast to int to avoid "peer id invalid" TypeError.
    try:
        chat_id    = int(chat_id)
        message_id = int(message_id)
    except (TypeError, ValueError) as e:
        log.error(f"Invalid chat_id/message_id for uid={uid}: {e}")
        raise HTTPException(500, "Invalid stream source data.")

    # ── Get file location info from Telegram ─────────────────────
    file_info = await get_file_info(chat_id, message_id)
    if not file_info:
        raise HTTPException(404, "File not accessible on Telegram.")

    # BUG FIX #4: file_size=0 files must still stream (e.g. photos reported as 0 by bot API)
    # Use file_info.file_size as ground truth if sheets recorded 0.
    if not size and file_info.file_size:
        size             = file_info.file_size
        from_b, until_b, status = _parse_range(range_hdr, size)
        content_length   = until_b - from_b + 1
        headers["Content-Length"] = str(content_length)

    # ── Stream ───────────────────────────────────────────────────
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
