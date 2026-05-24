"""
Pyrogram MTProto client.
Handles files > 20 MB by streaming directly from Telegram DCs.
"""
import asyncio
import logging
from typing import AsyncGenerator
from pyrogram import Client
from pyrogram.types import Message
import config

logger = logging.getLogger(__name__)

_client: Client | None = None

CHUNK_SIZE = 1024 * 1024   # 1 MB


def get_client() -> Client:
    global _client
    if _client is None:
        if not config.SESSION_STR:
            raise RuntimeError(
                "SESSION_STR env var is empty. "
                "Generate it first – see README."
            )
        _client = Client(
            name="tg_downloader",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=config.SESSION_STR,
            no_updates=True,
            in_memory=True,
        )
    return _client


async def start_client() -> None:
    client = get_client()
    if not client.is_connected:
        await client.start()
        me = await client.get_me()
        logger.info(f"Pyrogram logged in as {me.first_name} (id={me.id})")


async def stop_client() -> None:
    global _client
    if _client and _client.is_connected:
        await _client.stop()
        _client = None


async def stream_file(
    chat_id: int,
    message_id: int,
    offset: int = 0,
) -> AsyncGenerator[bytes, None]:
    """
    Yield raw bytes for a Telegram media message via MTProto.
    Supports Range requests through `offset`.
    Works for files up to 4 GB (Telegram Premium) / 2 GB (regular).

    FIX: stream_media() `limit` parameter is chunk COUNT not bytes.
         We no longer pass `limit` — let Pyrogram stream until end.
         For Range requests, we skip `offset` bytes at the start.
    """
    client = get_client()
    msg: Message = await client.get_messages(chat_id, message_id)
    if msg is None or not msg.media:
        raise ValueError("Message not found or has no media.")

    bytes_skipped = 0
    async for chunk in client.stream_media(msg):
        # Handle offset: skip bytes until we reach the requested start
        if offset > 0 and bytes_skipped < offset:
            remaining_to_skip = offset - bytes_skipped
            if len(chunk) <= remaining_to_skip:
                bytes_skipped += len(chunk)
                continue  # skip entire chunk
            else:
                # Partial skip
                chunk = chunk[remaining_to_skip:]
                bytes_skipped = offset

        yield chunk
