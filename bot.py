"""
python-telegram-bot handlers.
Receives files, stores metadata, replies with direct-download link.
"""
import logging
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)

import config
import store

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────

def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _build_link(unique_id: str, name: str) -> str:
    return f"{config.BASE_URL}/download/{unique_id}/{quote(name)}"


# ── Handlers ───────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *TG Direct Downloader*\n\n"
        "ඕනෑම file send කරන්න — direct link ලැබේ.\n\n"
        "• 20 MB以下 → Bot API (fast)\n"
        "• 20 MB+ → MTProto / Pyrogram (up to 4 GB)\n\n"
        "📌 Photos, videos, docs, audio, voice — ඔක්කොම OK!",
        parse_mode="Markdown",
    )


async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file_obj = None
    name     = "file"

    if msg.document:
        file_obj = msg.document
        name     = file_obj.file_name or f"doc_{file_obj.file_unique_id}"
    elif msg.video:
        file_obj = msg.video
        name     = getattr(file_obj, "file_name", None) or f"video_{file_obj.file_unique_id}.mp4"
    elif msg.audio:
        file_obj = msg.audio
        name     = file_obj.file_name or f"audio_{file_obj.file_unique_id}.mp3"
    elif msg.photo:
        file_obj = msg.photo[-1]
        name     = f"photo_{file_obj.file_unique_id}.jpg"
    elif msg.voice:
        file_obj = msg.voice
        name     = f"voice_{file_obj.file_unique_id}.ogg"
    elif msg.video_note:
        file_obj = msg.video_note
        name     = f"vidnote_{file_obj.file_unique_id}.mp4"
    elif msg.sticker:
        file_obj = msg.sticker
        ext  = "tgs" if file_obj.is_animated else ("webm" if file_obj.is_video else "webp")
        name = f"sticker_{file_obj.file_unique_id}.{ext}"

    if not file_obj:
        await msg.reply_text("❌ Supported file type එකක් send කරන්න.")
        return

    uid   = file_obj.file_unique_id
    fsize = getattr(file_obj, "file_size", 0) or 0
    big   = fsize > config.BOT_API_LIMIT

    store.save(uid, {
        "file_id":    file_obj.file_id,
        "file_name":  name,
        "file_size":  fsize,
        "chat_id":    msg.chat_id,
        "message_id": msg.message_id,
        "big":        big,
    })

    link = _build_link(uid, name)
    size_str = _human(fsize) if fsize else "Unknown"

    method_tag = (
        "⚡ MTProto (Pyrogram)" if big else "🤖 Bot API"
    )
    warn = "\n⚠️ Large file – MTProto streaming use කෙරේ." if big else ""

    kb = [[InlineKeyboardButton("⬇️ Direct Download", url=link)]]

    await msg.reply_text(
        f"✅ *Link Ready!*\n\n"
        f"📄 `{name}`\n"
        f"📦 {size_str}   {method_tag}{warn}\n\n"
        f"🔗 `{link}`",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


async def handle_other(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 File send කරන්න. /start for help.")


# ── App builder ────────────────────────────────────────────────────

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
