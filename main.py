import asyncio
import logging
import uvicorn
import config
import sheets
from stream_worker import start_client, stop_client
from server import app as fastapi_app
from bot import build_app

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def main():
    log.info("📊 Loading records from Google Sheets…")
    n = await sheets.load()
    log.info(f"📊 {n} records loaded")

    try:
        await start_client()
        log.info("✅ Telethon client ready")
    except Exception as e:
        log.error(f"❌ Telethon failed to start: {e}")
        raise

    # ── Uvicorn — same event loop, no threading ───────────────────
    # threading.Thread() වලින් uvicorn run කරද්දී uvicorn own loop
    # create කරනවා → Telethon "event loop must not change" crash.
    # Fix: uvicorn.Server directly use කරලා current loop share කරනවා.
    uv_config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=config.PORT,
        log_level="warning",
        access_log=False,
        loop="none",          # ← don't create a new loop
    )
    uv_server = uvicorn.Server(uv_config)

    log.info(f"✅ Web server on port {config.PORT}")

    # ── PTB bot ───────────────────────────────────────────────────
    ptb = build_app()
    await ptb.initialize()
    await ptb.start()
    await ptb.updater.start_polling(drop_pending_updates=True)
    log.info("✅ Bot polling started")

    # ── Run uvicorn + bot on same loop ────────────────────────────
    try:
        await uv_server.serve()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await ptb.updater.stop()
        await ptb.stop()
        await ptb.shutdown()
        await stop_client()


if __name__ == "__main__":
    asyncio.run(main())
