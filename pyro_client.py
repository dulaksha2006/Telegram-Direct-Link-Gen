"""
Pyrogram MTProto client.
FileToLink pattern follow කරමින් stream_media නිවැරදිව use කරනවා:
  - chunk_offset = offset // CHUNK_SIZE   (chunk index, bytes නෙමෙයි)
  - chunk_limit  = ceil(length / CHUNK_SIZE) + 1  (chunk count)
  - Stream generator එකේදී exact bytes clip කරනවා
"""
import asyncio
import logging
from typing import AsyncGenerator, Optional

from pyrogram import Client
from pyrogram.errors import FloodWait

import config

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB — Pyrogram internal chunk size

_client: Optional[Client] = None


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
    limit: int = 0,          # bytes; 0 = end of file
) -> AsyncGenerator[bytes, None]:
    """
    FileToLink pattern:
      chunk_offset = offset // CHUNK_SIZE
      chunk_limit  = ((limit + CHUNK_SIZE - 1) // CHUNK_SIZE) + 1
    
    Stream generator clips exact bytes:
      - leading bytes_to_skip  (offset % CHUNK_SIZE)
      - trailing clip to content_length
    """
    client = get_client()

    # Retry on FloodWait
    while True:
        try:
            msg = await client.get_messages(chat_id, message_id)
            break
        except FloodWait as e:
            logger.debug(f"FloodWait get_messages: sleep {e.value}s")
            await asyncio.sleep(e.value)

    if msg is None or not msg.media:
        raise ValueError(f"Message {message_id} not found or has no media.")

    chunk_offset = offset // CHUNK_SIZE
    chunk_limit  = 0
    if limit > 0:
        chunk_limit = ((limit + CHUNK_SIZE - 1) // CHUNK_SIZE) + 1

    bytes_to_skip = offset % CHUNK_SIZE
    bytes_sent    = 0

    while True:
        try:
            async for chunk in client.stream_media(
                msg, offset=chunk_offset, limit=chunk_limit
            ):
                # Skip leading bytes (alignment)
                if bytes_to_skip > 0:
                    if len(chunk) <= bytes_to_skip:
                        bytes_to_skip -= len(chunk)
                        continue
                    chunk = chunk[bytes_to_skip:]
                    bytes_to_skip = 0

                # Clip trailing bytes
                if limit > 0:
                    remaining = limit - bytes_sent
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]

                if chunk:
                    yield chunk
                    bytes_sent += len(chunk)

                if limit > 0 and bytes_sent >= limit:
                    return
            return
        except FloodWait as e:
            logger.debug(f"FloodWait stream_media: sleep {e.value}s")
            await asyncio.sleep(e.value)


async def forward_to_storage(
    chat_id: int,
    message_id: int,
    storage_channel: int,
) -> Optional[int]:
    """
    File message එක STORAGE_CHANNEL එකට forward කරනවා.
    Returns forwarded message_id (persistent!) or None on failure.
    """
    client = get_client()
    while True:
        try:
            fwd = await client.forward_messages(
                chat_id=storage_channel,
                from_chat_id=chat_id,
                message_ids=message_id,
            )
            # forward_messages returns list or single Message
            if isinstance(fwd, list):
                fwd = fwd[0]
            return fwd.id
        except FloodWait as e:
            logger.debug(f"FloodWait forward: sleep {e.value}s")
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Forward failed: {e}", exc_info=True)
            return None
