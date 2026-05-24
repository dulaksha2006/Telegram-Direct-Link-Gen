"""
Entry point.
Startup sequence:
  1. Google Sheets → memory cache load (restart-safe file records)
  2. Pyrogram MTProto client start
  3. FastAPI (uvicorn) background thread
  4. python-telegram-bot polling
"""
import asyncio
import logging
import threading

import uvicorn

import config
import sheets
from pyro_client import start_client, stop_client
from server import app as fastapi_app
from bot import build_app

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _run_web() -> None:
    uvicorn.run(
        fastapi_app,
        host="0.0.0.0",
        port=config.PORT,
        log_level="warning",
        access_log=False,
    )


async def main() -> None:
    # 1. Load Google Sheets → cache
    logger.info("📊 Loading file records from Google Sheets…")
    count = await sheets.load()
    logger.info(f"📊 {count} file records loaded (restart-safe)")

    # 2. Start Pyrogram
    try:
        await start_client()
        logger.info("✅ Pyrogram MTProto client ready")
    except Exception as exc:
        logger.warning(f"⚠️  Pyrogram not started ({exc}). Large file streaming disabled.")

    # 3. FastAPI web server
    web_thread = threading.Thread(target=_run_web, daemon=True)
    web_thread.start()
    logger.info(f"✅ FastAPI server on port {config.PORT}")

    # 4. Telegram bot polling
    ptb_app = build_app()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.updater.start_polling(drop_pending_updates=True)
    logger.info("✅ Telegram bot polling started")

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Shutting down…")
        await ptb_app.updater.stop()
        await ptb_app.stop()
        await ptb_app.shutdown()
        await stop_client()


if __name__ == "__main__":
    asyncio.run(main())
