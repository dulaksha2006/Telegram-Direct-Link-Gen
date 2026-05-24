"""
Google Sheets store via Apps Script Web App URL.

Setup:
  1. Google Sheet create කරන්න
  2. Extensions → Apps Script → paste appsscript_code.gs
  3. Deploy → New deployment → Web app
       Execute as: Me
       Who has access: Anyone
  4. Web App URL copy → SHEETS_WEBHOOK_URL env var

Sheet columns:
  A: unique_id
  B: file_name
  C: file_size
  D: channel_msg_id
  E: chat_id
  F: message_id
  G: big (TRUE/FALSE)
  H: added_at
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx

import config

logger = logging.getLogger(__name__)

_cache: dict[str, dict] = {}


async def _request(payload: dict) -> dict:
    """POST to Apps Script Web App."""
    if not config.SHEETS_WEBHOOK_URL:
        return {"status": "no_url"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.post(config.SHEETS_WEBHOOK_URL, json=payload)
        r.raise_for_status()
        return r.json()


async def load() -> int:
    """Startup: fetch all rows from sheet → memory cache."""
    if not config.SHEETS_WEBHOOK_URL:
        logger.warning("SHEETS_WEBHOOK_URL not set — restart-safe storage disabled.")
        return 0
    try:
        data = await _request({"action": "getAll"})
        rows = data.get("rows", [])
        loaded = 0
        for row in rows:
            uid = row.get("unique_id")
            if uid:
                _cache[uid] = {
                    "file_name":      row.get("file_name", ""),
                    "file_size":      int(row.get("file_size") or 0),
                    "channel_msg_id": int(row["channel_msg_id"]) if row.get("channel_msg_id") else None,
                    "chat_id":        int(row["chat_id"]) if row.get("chat_id") else None,
                    "message_id":     int(row["message_id"]) if row.get("message_id") else None,
                    "big":            str(row.get("big", "")).upper() == "TRUE",
                }
                loaded += 1
        logger.info(f"✅ Loaded {loaded} file records from Google Sheets")
        return loaded
    except Exception as e:
        logger.error(f"Failed to load from Google Sheets: {e}", exc_info=True)
        return 0


def get(unique_id: str) -> Optional[dict]:
    return _cache.get(unique_id)


async def save(unique_id: str, info: dict) -> bool:
    _cache[unique_id] = info  # instant cache
    if not config.SHEETS_WEBHOOK_URL:
        return True
    try:
        await _request({
            "action":         "append",
            "unique_id":      unique_id,
            "file_name":      info.get("file_name", ""),
            "file_size":      str(info.get("file_size", 0)),
            "channel_msg_id": str(info.get("channel_msg_id") or ""),
            "chat_id":        str(info.get("chat_id") or ""),
            "message_id":     str(info.get("message_id") or ""),
            "big":            "TRUE" if info.get("big") else "FALSE",
            "added_at":       datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"📊 Saved {info.get('file_name','?')} to Google Sheets")
        return True
    except Exception as e:
        logger.error(f"Failed to save to Google Sheets: {e}", exc_info=True)
        return False


async def update_channel_msg_id(unique_id: str, channel_msg_id: int) -> None:
    if unique_id in _cache:
        _cache[unique_id]["channel_msg_id"] = channel_msg_id
    if not config.SHEETS_WEBHOOK_URL:
        return
    try:
        await _request({
            "action":         "update",
            "unique_id":      unique_id,
            "channel_msg_id": str(channel_msg_id),
        })
    except Exception as e:
        logger.warning(f"Could not update channel_msg_id in sheet: {e}")
