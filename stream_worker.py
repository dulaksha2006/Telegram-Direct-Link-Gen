"""
Telegram file streamer using Telethon + raw GetFileRequest.
Taken from TG-FileStreamBot (EverythingSuckz/SpringsFern) proven working approach.

Pyrogram's stream_media() has known issues with range requests / partial downloads.
This uses Telethon's low-level MTProto GetFileRequest directly — no such issues.
"""
import asyncio
import copy
import logging
import math
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Union

from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.errors import DcIdInvalidError
from telethon.network import MTProtoSender
from telethon.tl import types
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.patched import Message
from telethon.utils import get_input_location

import config

log = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB — Telegram's max chunk size

# ── Telethon client ───────────────────────────────────────────────
_client: Optional[TelegramClient] = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            session=None,         # in-memory session (use string session)
            api_id=config.API_ID,
            api_hash=config.API_HASH,
        )
    return _client


async def start_client() -> None:
    client = get_client()
    if not client.is_connected():
        await client.start(bot_token=config.BOT_TOKEN)
        me = await client.get_me()
        log.info(f"Telethon connected as {me.first_name} (bot)")
        _transfer_cache.clear()


async def stop_client() -> None:
    global _client
    if _client and _client.is_connected():
        await _client.disconnect()
        _client = None


# ── File info ─────────────────────────────────────────────────────
@dataclass
class FileInfo:
    file_size: int
    mime_type: str
    file_name: str
    dc_id: int
    location: Union[types.InputPhotoFileLocation, types.InputDocumentFileLocation]


async def get_file_info(chat_id: int, message_id: int) -> Optional[FileInfo]:
    client = get_client()
    msg: Message = await client.get_messages(chat_id, ids=message_id)
    if not msg or not msg.media:
        return None
    try:
        media = msg.media
        file  = getattr(media, "document", None) or getattr(media, "photo", None)
        dc_id, location = get_input_location(media)
        return FileInfo(
            file_size = msg.file.size or 0,
            mime_type = msg.file.mime_type or "application/octet-stream",
            file_name = getattr(msg.file, "name", None) or f"file_{message_id}",
            dc_id     = dc_id,
            location  = location,
        )
    except Exception as e:
        log.error(f"get_file_info error: {e}", exc_info=True)
        return None


# ── DC Connection Manager ─────────────────────────────────────────
class DCConn:
    def __init__(self, client: TelegramClient, dc_id: int):
        self.client   = client
        self.dc_id    = dc_id
        self.sender:  Optional[MTProtoSender] = None
        self.auth_key: Optional[AuthKey]      = None
        self._lock    = asyncio.Lock()

    async def ensure_connected(self) -> MTProtoSender:
        async with self._lock:
            if self.sender and self.sender.is_connected():
                return self.sender

            dc = await self.client._get_dc(self.dc_id)
            sender = MTProtoSender(self.auth_key, loggers=self.client._log)
            conn_info = self.client._connection(
                dc.ip_address, dc.port, dc.id,
                loggers=self.client._log,
                proxy=self.client._proxy,
            )
            await sender.connect(conn_info)

            if not self.auth_key:
                try:
                    auth = await self.client(ExportAuthorizationRequest(self.dc_id))
                    init_req = copy.copy(self.client._init_request)
                    init_req.query = ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes)
                    await sender.send(InvokeWithLayerRequest(LAYER, init_req))
                    self.auth_key = sender.auth_key
                except DcIdInvalidError:
                    # same DC — reuse session key
                    self.auth_key = self.client.session.auth_key
                    sender.auth_key = self.auth_key

            self.sender = sender
            return sender


_dc_conns: dict[int, DCConn] = {}
_transfer_cache: dict[int, "Transferrer"] = {}   # client_id → Transferrer


def _get_dc_conn(dc_id: int) -> DCConn:
    if dc_id not in _dc_conns:
        _dc_conns[dc_id] = DCConn(get_client(), dc_id)
    return _dc_conns[dc_id]


# ── Streamer ──────────────────────────────────────────────────────
async def stream_file(
    file_info: FileInfo,
    from_bytes: int = 0,
    until_bytes: Optional[int] = None,
) -> AsyncGenerator[bytes, None]:
    """
    Stream file bytes using raw MTProto GetFileRequest.
    from_bytes / until_bytes are BYTE offsets (inclusive).
    """
    file_size  = file_info.file_size
    until_bytes = (until_bytes if until_bytes is not None else file_size - 1)
    until_bytes = min(until_bytes, file_size - 1)

    # Align offset down to chunk boundary
    offset          = from_bytes - (from_bytes % CHUNK_SIZE)
    first_part_cut  = from_bytes - offset            # bytes to skip in first chunk
    last_part_cut   = until_bytes % CHUNK_SIZE + 1   # bytes to keep in last chunk
    first_part      = math.floor(offset / CHUNK_SIZE)
    last_part       = math.ceil(until_bytes / CHUNK_SIZE)
    part_count      = last_part - first_part

    dc_conn = _get_dc_conn(file_info.dc_id)
    sender  = await dc_conn.ensure_connected()

    request = GetFileRequest(file_info.location, offset=offset, limit=CHUNK_SIZE)

    for current_part in range(1, part_count + 1):
        result = await sender.send(request)
        request.offset += CHUNK_SIZE

        if not result.bytes:
            log.warning(f"Empty chunk at part {current_part}/{part_count}")
            break

        chunk = result.bytes

        if part_count == 1:
            chunk = chunk[first_part_cut:last_part_cut]
        elif current_part == 1:
            chunk = chunk[first_part_cut:]
        elif current_part == part_count:
            chunk = chunk[:last_part_cut]

        if chunk:
            yield chunk


# ── Forward to storage channel ────────────────────────────────────
async def forward_to_storage(chat_id: int, message_id: int) -> Optional[int]:
    """Forward message to STORAGE_CHANNEL. Returns new message_id or None."""
    client = get_client()
    try:
        result = await client.forward_messages(
            entity=config.STORAGE_CHANNEL,
            messages=message_id,
            from_peer=chat_id,
        )
        msgs = result if isinstance(result, list) else [result]
        return msgs[0].id if msgs else None
    except Exception as e:
        log.error(f"Forward failed: {e}", exc_info=True)
        return None
