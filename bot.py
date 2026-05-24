"""
python-telegram-bot handlers.
File receive → forward to STORAGE_CHANNEL → Google Sheet save → direct link reply.
"""
import asyncio
import logging
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)

import config
import sheets
from pyro_client import forward_to_storage

logger = logging.getLogger(__name__)


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _build_link(unique_id: str, name: str) -> str:
    return f"{config.BASE_URL}/download/{unique_id}/{quote(name)}"


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *TG Direct Downloader*\n\n"
        "ඕනෑම file send කරන්න — direct link ලැබේ.\n\n"
        "• 20 MB以下 → Bot API (fast)\n"
        "• 20 MB+ → MTProto / Pyrogram (up to 4 GB)\n\n"
        "📌 Bot restart වෙද්දීත් links valid — Google Sheet backup!",
        parse_mode="Markdown",
    )


async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file_obj = None
    name = "file"

    if msg.document:
        file_obj = msg.document
        name = file_obj.file_name or f"doc_{file_obj.file_unique_id}"
    elif msg.video:
        file_obj = msg.video
        name = getattr(file_obj, "file_name", None) or f"video_{file_obj.file_unique_id}.mp4"
    elif msg.audio:
        file_obj = msg.audio
        name = file_obj.file_name or f"audio_{file_obj.file_unique_id}.mp3"
    elif msg.photo:
        file_obj = msg.photo[-1]
        name = f"photo_{file_obj.file_unique_id}.jpg"
    elif msg.voice:
        file_obj = msg.voice
        name = f"voice_{file_obj.file_unique_id}.ogg"
    elif msg.video_note:
        file_obj = msg.video_note
        name = f"vidnote_{file_obj.file_unique_id}.mp4"
    elif msg.sticker:
        file_obj = msg.sticker
        ext = "tgs" if file_obj.is_animated else ("webm" if file_obj.is_video else "webp")
        name = f"sticker_{file_obj.file_unique_id}.{ext}"

    if not file_obj:
        await msg.reply_text("❌ Supported file type එකක් send කරන්න.")
        return

    uid   = file_obj.file_unique_id
    fsize = getattr(file_obj, "file_size", 0) or 0
    big   = fsize > config.BOT_API_LIMIT

    # ── Processing message ──────────────────────────────────────
    status = await msg.reply_text("⏳ Processing...")

    # ── Forward to STORAGE_CHANNEL via Pyrogram ─────────────────
    channel_msg_id = None
    if config.SESSION_STR:
        channel_msg_id = await forward_to_storage(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            storage_channel=config.STORAGE_CHANNEL,
        )
        if channel_msg_id:
            logger.info(f"Forwarded to storage channel: msg_id={channel_msg_id}")
        else:
            logger.warning("Forward to storage channel failed, using original message.")

    # ── Build info dict ──────────────────────────────────────────
    info = {
        "file_id":        file_obj.file_id,
        "file_name":      name,
        "file_size":      fsize,
        "chat_id":        msg.chat_id,
        "message_id":     msg.message_id,
        "channel_msg_id": channel_msg_id,
        "big":            big,
    }

    # ── Persist to Google Sheets + memory cache ──────────────────
    await sheets.save(uid, info)

    # ── Build direct link ────────────────────────────────────────
    link     = _build_link(uid, name)
    size_str = _human(fsize) if fsize else "Unknown"
    method   = "⚡ MTProto (Pyrogram)" if big else "🤖 Bot API"
    stored   = "✅ Stored in channel + Sheet" if channel_msg_id else "⚠️ Sheet only"
    warn     = "\n⚠️ Large file – MTProto streaming use කෙරේ." if big else ""

    kb = [[InlineKeyboardButton("⬇️ Direct Download", url=link)]]

    try:
        await status.edit_text(
            f"✅ *Link Ready!*\n\n"
            f"📄 `{name}`\n"
            f"📦 {size_str}   {method}{warn}\n"
            f"💾 {stored}\n\n"
            f"🔗 `{link}`",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )
    except Exception:
        await msg.reply_text(
            f"✅ *Link Ready!*\n\n"
            f"📄 `{name}`\n"
            f"📦 {size_str}   {method}{warn}\n\n"
            f"🔗 `{link}`",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown",
        )


async def handle_other(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 File send කරන්න. /start for help.")


def build_app() -> Application:
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(
        filters.Document.ALL
        | filters.VIDEO
        | filters.AUDIO
        | filters.PHOTO
        | filters.VOICE
        | filters.VIDEO_NOTE
        | filters.Sticker.ALL,
        handle_media,
    ))
    app.add_handler(MessageHandler(filters.ALL, handle_other))
    return app
