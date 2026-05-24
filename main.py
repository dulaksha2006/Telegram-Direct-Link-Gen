import asyncio, logging, threading
import uvicorn
import config, sheets
from stream_worker import start_client, stop_client
from server import app as fastapi_app
from bot import build_app

logging.basicConfig(format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


def _run_web():
    uvicorn.run(fastapi_app, host="0.0.0.0", port=config.PORT, log_level="warning", access_log=False)


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

    threading.Thread(target=_run_web, daemon=True).start()
    log.info(f"✅ Web server on port {config.PORT}")

    ptb = build_app()
    await ptb.initialize()
    await ptb.start()
    await ptb.updater.start_polling(drop_pending_updates=True)
    log.info("✅ Bot polling started")

    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await ptb.updater.stop()
        await ptb.stop()
        await ptb.shutdown()
        await stop_client()


if __name__ == "__main__":
    asyncio.run(main())
