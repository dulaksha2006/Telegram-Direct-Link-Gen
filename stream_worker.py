"""
Telegram file streamer using Telethon + raw GetFileRequest.
"""
import asyncio
import copy
import logging
import math
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Union

from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.errors import DcIdInvalidError, ChannelPrivateError, ChatAdminRequiredError
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

CHUNK_SIZE = 1024 * 1024  # 1 MB

_client: Optional[TelegramClient] = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            session=None,
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
        _dc_conns.clear()


async def stop_client() -> None:
    global _client
    if _client and _client.is_connected():
        await _client.disconnect()
        _client = None


@dataclass
class FileInfo:
    file_size: int
    mime_type: str
    file_name: str
    dc_id: int
    location: Union[types.InputPhotoFileLocation, types.InputDocumentFileLocation]


async def _fetch_msg(chat_id: int, message_id: int) -> Optional[Message]:
    """Fetch a single message with detailed error logging."""
    client = get_client()
    try:
        msg = await client.get_messages(chat_id, ids=message_id)
        if msg is None:
            log.warning(
                f"get_messages returned None — "
                f"chat_id={chat_id} msg_id={message_id}. "
                f"Possible causes: bot not in channel, wrong chat_id, message deleted."
            )
        elif not msg.media:
            log.warning(
                f"Message has no media — "
                f"chat_id={chat_id} msg_id={message_id} "
                f"msg_type={type(msg).__name__}"
            )
        return msg
    except (ChannelPrivateError, ChatAdminRequiredError) as e:
        log.error(
            f"Bot has no access to chat_id={chat_id}: {e}. "
            f"Bot must be admin in the storage channel!"
        )
        return None
    except Exception as e:
        log.error(
            f"get_messages failed chat_id={chat_id} msg_id={message_id}: {e}",
            exc_info=True
        )
        return None


async def get_file_info(
    chat_id: int,
    message_id: int,
    fallback_chat_id: Optional[int] = None,
    fallback_message_id: Optional[int] = None,
) -> Optional["FileInfo"]:
    """
    Try primary (storage channel) first.
    If it fails, fall back to original chat/message.
    This prevents "File not accessible" when bot loses access to storage channel.
    """
    # ── Primary attempt ───────────────────────────────────────────
    msg = await _fetch_msg(chat_id, message_id)

    # ── Fallback to original chat ─────────────────────────────────
    if (not msg or not msg.media) and fallback_chat_id and fallback_message_id:
        log.info(
            f"Primary source failed (chat={chat_id}, msg={message_id}), "
            f"trying fallback (chat={fallback_chat_id}, msg={fallback_message_id})"
        )
        msg = await _fetch_msg(fallback_chat_id, fallback_message_id)

    if not msg or not msg.media:
        log.error(
            f"All sources failed. Primary: chat={chat_id} msg={message_id} | "
            f"Fallback: chat={fallback_chat_id} msg={fallback_message_id}"
        )
        return None

    try:
        dc_id, location = get_input_location(msg.media)
        return FileInfo(
            file_size = msg.file.size or 0,
            mime_type = msg.file.mime_type or "application/octet-stream",
            file_name = getattr(msg.file, "name", None) or f"file_{message_id}",
            dc_id     = dc_id,
            location  = location,
        )
    except Exception as e:
        log.error(f"get_input_location error: {e}", exc_info=True)
        return None


# ── DC Connection Manager ─────────────────────────────────────────
class DCConn:
    def __init__(self, client: TelegramClient, dc_id: int):
        self.client    = client
        self.dc_id     = dc_id
        self.sender:   Optional[MTProtoSender] = None
        self.auth_key: Optional[AuthKey]       = None
        self._lock     = asyncio.Lock()

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
                    self.auth_key = self.client.session.auth_key
                    sender.auth_key = self.auth_key

            self.sender = sender
            return sender


_dc_conns: dict[int, DCConn] = {}


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
    file_size   = file_info.file_size
    until_bytes = (until_bytes if until_bytes is not None else file_size - 1)
    until_bytes = min(until_bytes, file_size - 1)

    offset         = from_bytes - (from_bytes % CHUNK_SIZE)
    first_part_cut = from_bytes - offset
    last_part_cut  = until_bytes % CHUNK_SIZE + 1
    first_part     = math.floor(offset / CHUNK_SIZE)
    last_part      = math.ceil(until_bytes / CHUNK_SIZE)
    part_count     = last_part - first_part

    if part_count == 0:
        part_count = 1

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
