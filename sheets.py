"""
Google Sheets store via Apps Script Web App URL.

Sheet columns:
  A: unique_id
  B: file_name
  C: file_size
  D: channel_msg_id
  E: chat_id
  F: message_id
  G: big (TRUE/FALSE)
  H: added_at
  I: mime_type
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


def _parse_row(row: dict) -> dict:
    """Normalize a raw sheet row into typed cache entry."""
    return {
        "file_name":      row.get("file_name", ""),
        "file_size":      int(row.get("file_size") or 0),
        "channel_msg_id": int(row["channel_msg_id"]) if row.get("channel_msg_id") else None,
        "chat_id":        int(row["chat_id"]) if row.get("chat_id") else None,
        "message_id":     int(row["message_id"]) if row.get("message_id") else None,
        "big":            str(row.get("big", "")).upper() == "TRUE",
        "mime_type":      row.get("mime_type") or None,
    }


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
                _cache[uid] = _parse_row(row)
                loaded += 1
        logger.info(f"✅ Loaded {loaded} file records from Google Sheets")
        return loaded
    except Exception as e:
        logger.error(f"Failed to load from Google Sheets: {e}", exc_info=True)
        return 0


async def _fetch_one(unique_id: str) -> Optional[dict]:
    """
    Fetch a single record from Sheets by unique_id.
    Used as fallback when cache misses (e.g. after restart before full load).
    """
    try:
        data = await _request({"action": "getOne", "unique_id": unique_id})
        row  = data.get("row")
        if row and row.get("unique_id"):
            parsed = _parse_row(row)
            _cache[unique_id] = parsed   # warm cache
            logger.info(f"📊 Lazy-loaded uid={unique_id} from Sheets")
            return parsed
    except Exception as e:
        logger.warning(f"Lazy fetch failed for uid={unique_id}: {e}")
    return None


def get(unique_id: str) -> Optional[dict]:
    """Sync cache lookup — returns None if not in memory (caller should use aget)."""
    return _cache.get(unique_id)


async def aget(unique_id: str) -> Optional[dict]:
    """
    Async get: cache first, then lazy Sheets fetch.
    Always use this in request handlers so bot restart doesn't break old links.
    """
    entry = _cache.get(unique_id)
    if entry:
        return entry
    return await _fetch_one(unique_id)


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
            "mime_type":      info.get("mime_type") or "",
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
