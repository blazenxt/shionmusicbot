"""ShionMusicBot entrypoint — ``python3 -m anony``.

Boot sequence
-------------
1. ensure runtime directories + logging
2. validate configuration (explicit errors on missing credentials)
3. restore persisted state, start assistant → bot → PyTgCalls
4. wire the stream-end hook to the queue engine
5. start the dashboard metrics writer, then idle until shutdown
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import pkgutil
import sys
import time

import anony
from anony import BOOT_TIME, bot, call, db, lang, userbot
from anony.core import dir as dirutil
from anony.core.youtube import youtube
from anony.helpers._player import on_stream_end
from config import config, validate

log = logging.getLogger("anony.boot")


def setup_logging() -> None:
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        dirutil.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    for noisy in ("pyrogram", "pytgcalls", "ntgcalls", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def _build_status(active_chats: list, queues: dict) -> dict:
    try:
        import psutil

        process = psutil.Process()
        cpu = process.cpu_percent()
        mem = process.memory_info().rss / 1_048_576
        sys_cpu = psutil.cpu_percent(interval=None)
        sys_mem = psutil.virtual_memory().percent
    except Exception:  # noqa: BLE001 - metrics are best effort
        cpu = mem = sys_cpu = sys_mem = -1

    import pyrogram
    import pytgcalls

    return {
        "status": "online",
        "ts": int(time.time()),
        "boot": int(BOOT_TIME),
        "uptime": int(time.time() - BOOT_TIME),
        "pid": os.getpid(),
        "bot": f"@{getattr(bot, 'username', config.BOT_USERNAME)}",
        "assistant": f"@{config.ASSISTANT_USERNAME}",
        "py": sys.version.split()[0],
        "pyrogram": pyrogram.__version__,
        "pytgcalls": pytgcalls.__version__,
        "active_calls": active_chats,
        "queues": queues,
        "chats": len(await db.get_chats()),
        "users": len(await db.get_users()),
        "plays": await db.get_counter("plays"),
        "cpu": cpu,
        "mem_mb": round(mem, 1),
        "sys_cpu": sys_cpu,
        "sys_mem": sys_mem,
    }


async def status_writer() -> None:
    """Publish ``web_status.json`` for the web dashboard every 20 s."""
    from anony.helpers._queue import queue

    while True:
        try:
            active = await call.active_chats()
            queues = {str(cid): len(items) for cid, items in queue.all().items()}
            payload = await _build_status(active, queues)
            tmp = str(dirutil.WEB_STATUS) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, str(dirutil.WEB_STATUS))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("status writer iteration failed")
        await asyncio.sleep(20)


async def main() -> None:
    dirutil.ensure_dirs()
    setup_logging()

    problems = validate()
    if problems:
        for problem in problems:
            log.error("Configuration error: %s", problem)
        sys.exit(1)

    log.info("ShionMusicBot v%s booting…", anony.__version__)
    db.load()

    # Assistant first — PyTgCalls wraps it and completes the start if needed.
    await userbot.start()
    await bot.start()

    if config.assistant_session:
        await call.start()
        call.on_stream_end(on_stream_end)
    else:
        log.warning("Skipping PyTgCalls start (no assistant session configured).")

    import anony.plugins

    plugin_count = len(list(pkgutil.iter_modules(anony.plugins.__path__)))
    log.info("Loaded %d modules.", plugin_count)

    writer = asyncio.create_task(status_writer())

    from pyrogram import idle

    await idle()

    log.info("Shutting down…")
    writer.cancel()
    try:
        await asyncio.wait_for(call.stop_all(), timeout=10)
    except Exception:  # noqa: BLE001
        pass
    db.save()
    for client, name in ((bot, "bot"), (userbot, "assistant")):
        try:
            await client.stop()
        except Exception:  # noqa: BLE001
            pass
    await youtube.close()
    log.info("Shutdown complete. Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
