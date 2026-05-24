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
            no_updates=True,          # we only download, no need for updates
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
    chunk_size: int = 1024 * 1024,   # 1 MB chunks
) -> AsyncGenerator[bytes, None]:
    """
    Yield raw bytes for a Telegram media message via MTProto.
    Supports Range requests through `offset`.
    Works for files up to 4 GB (Telegram Premium) / 2 GB (regular).
    """
    client = get_client()
    msg: Message = await client.get_messages(chat_id, message_id)
    if msg is None or not msg.media:
        raise ValueError("Message not found or has no media.")

    async for chunk in client.stream_media(msg, offset=offset, limit=chunk_size):
        yield chunk
