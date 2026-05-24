"""
python-telegram-bot handlers.
File receive → forward to STORAGE_CHANNEL → Google Sheet → reply link.
"""
import asyncio
import logging
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import config
import sheets
from stream_worker import forward_to_storage

log = logging.getLogger(__name__)


def _human(size: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if size < 1024: return f"{size:.1f} {u}"
        size /= 1024
    return f"{size:.1f} TB"


def _link(uid: str, name: str) -> str:
    return f"{config.BASE_URL}/download/{uid}/{quote(name)}"


async def cmd_start(update: Update, _):
    await update.message.reply_text(
        "🚀 *TG Direct Downloader*\n\n"
        "ඕනෑම file send කරන්න → direct link ලැබේ.\n\n"
        "• Bot restart වෙද්දීත් links live ✅",
        parse_mode="Markdown",
    )


async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    f = None
    name = "file"

    if msg.document:
        f = msg.document; name = f.file_name or f"doc_{f.file_unique_id}"
    elif msg.video:
        f = msg.video; name = getattr(f, "file_name", None) or f"video_{f.file_unique_id}.mp4"
    elif msg.audio:
        f = msg.audio; name = f.file_name or f"audio_{f.file_unique_id}.mp3"
    elif msg.photo:
        f = msg.photo[-1]; name = f"photo_{f.file_unique_id}.jpg"
    elif msg.voice:
        f = msg.voice; name = f"voice_{f.file_unique_id}.ogg"
    elif msg.video_note:
        f = msg.video_note; name = f"vidnote_{f.file_unique_id}.mp4"
    elif msg.sticker:
        f = msg.sticker
        ext = "tgs" if f.is_animated else ("webm" if f.is_video else "webp")
        name = f"sticker_{f.file_unique_id}.{ext}"

    if not f:
        await msg.reply_text("❌ Supported file type එකක් send කරන්න.")
        return

    uid   = f.file_unique_id
    fsize = getattr(f, "file_size", 0) or 0
    big   = fsize > config.BOT_API_LIMIT

    # Mime type from document if available
    mime_type = getattr(f, "mime_type", None)

    status = await msg.reply_text("⏳ Processing...")

    # ── Forward to STORAGE_CHANNEL ────────────────────────────────
    channel_msg_id = await forward_to_storage(msg.chat_id, msg.message_id)
    if channel_msg_id:
        log.info(f"Forwarded → storage channel msg_id={channel_msg_id}")
    else:
        log.warning("Forward to storage channel failed.")

    # ── Save to Sheets + cache ────────────────────────────────────
    info = {
        "file_name":      name,
        "file_size":      fsize,
        "mime_type":      mime_type,
        "chat_id":        msg.chat_id,
        "message_id":     msg.message_id,
        "channel_msg_id": channel_msg_id,
        "big":            big,
    }
    await sheets.save(uid, info)

    link     = _link(uid, name)
    size_str = _human(fsize) if fsize else "Unknown"
    stored   = "✅ Channel + Sheet" if channel_msg_id else "⚠️ Sheet only"

    try:
        await status.edit_text(
            f"✅ *Link Ready!*\n\n"
            f"📄 `{name}`\n"
            f"📦 {size_str}\n"
            f"💾 {stored}\n\n"
            f"🔗 `{link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ Download", url=link)]]),
            parse_mode="Markdown",
        )
    except Exception:
        await msg.reply_text(f"🔗 `{link}`", parse_mode="Markdown")


async def handle_other(update: Update, _):
    await update.message.reply_text("📁 File send කරන්න.")


def build_app() -> Application:
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO |
        filters.PHOTO | filters.VOICE | filters.VIDEO_NOTE | filters.Sticker.ALL,
        handle_media,
    ))
    app.add_handler(MessageHandler(filters.ALL, handle_other))
    return app
