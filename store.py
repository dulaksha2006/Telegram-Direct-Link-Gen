"""
Simple in-memory file store.
Keys : file_unique_id  (str)
Value: dict {
    file_id   : str   – Telegram file_id
    file_name : str
    file_size : int   – bytes
    chat_id   : int   – originating chat (needed for Pyrogram streaming)
    message_id: int   – originating message
    big       : bool  – True when > BOT_API_LIMIT
}

NOTE: data is lost on process restart.
For persistence add Redis:  pip install redis  and replace dict with Redis hashes.
"""

_store: dict[str, dict] = {}


def save(unique_id: str, data: dict) -> None:
    _store[unique_id] = data


def get(unique_id: str) -> dict | None:
    return _store.get(unique_id)


def all_keys() -> list[str]:
    return list(_store.keys())
