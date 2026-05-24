"""
Entry point.
Starts:
  1. Pyrogram MTProto client
  2. Uvicorn (FastAPI) in a background thread
  3. python-telegram-bot polling in the main event loop
"""
import asyncio
import logging
import threading

import uvicorn

import config
from pyro_client import start_client, stop_client
from server import app as fastapi_app
from bot import build_app

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _run_web() -> None:
    """Run FastAPI in its own thread (blocking)."""
    uvicorn.run(
        fastapi_app,
        host="0.0.0.0",
        port=config.PORT,
        log_level="warning",
        access_log=False,
    )


async def main() -> None:
    # 1. Start Pyrogram
    try:
        await start_client()
        logger.info("✅ Pyrogram MTProto client ready")
    except Exception as exc:
        logger.warning(f"⚠️  Pyrogram not started ({exc}). 20 MB+ downloads disabled.")

    # 2. Start FastAPI web server in background thread
    web_thread = threading.Thread(target=_run_web, daemon=True)
    web_thread.start()
    logger.info(f"✅ FastAPI server started on port {config.PORT}")

    # 3. Start telegram bot (polling)
    ptb_app = build_app()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.updater.start_polling(drop_pending_updates=True)
    logger.info("✅ Telegram bot polling started")

    # 4. Block until interrupted
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
