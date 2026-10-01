"""ShionMusicBot entrypoint — ``python3 -m anony``."""

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
    if root.handlers:
        root.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        dirutil.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if sys.stdout.isatty():
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)

    for noisy in ("pyrogram", "pytgcalls", "ntgcalls", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _write_private_json(name: str, payload: dict) -> None:
    path = dirutil.RUNTIME / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


async def _build_status(active_chats: list, queues: dict, assistant_ready: bool) -> dict:
    try:
        import psutil

        process = psutil.Process()
        cpu = process.cpu_percent()
        mem = process.memory_info().rss / 1_048_576
        sys_cpu = psutil.cpu_percent(interval=None)
        sys_mem = psutil.virtual_memory().percent
    except Exception:
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
        "assistant_ready": assistant_ready,
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


async def status_writer(assistant_ready: bool) -> None:
    from anony.helpers._queue import queue

    while True:
        try:
            active = await call.active_chats() if assistant_ready else []
            queues = {str(cid): len(items) for cid, items in queue.all().items()}
            payload = await _build_status(active, queues, assistant_ready)
            tmp = str(dirutil.WEB_STATUS) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, str(dirutil.WEB_STATUS))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("status writer iteration failed")
        await asyncio.sleep(20)


async def _start_assistant() -> bool:
    if not config.assistant_session:
        dirutil.SESSION_REQUIRED.touch(exist_ok=True)
        log.warning("Assistant session is not configured; starting bot-only mode.")
        return False
    if dirutil.SESSION_REQUIRED.exists():
        log.warning("Assistant session needs login; starting bot-only mode.")
        return False

    try:
        await asyncio.wait_for(userbot.start(), timeout=45)
        await asyncio.wait_for(call.start(), timeout=45)
        call.on_stream_end(on_stream_end)
        dirutil.SESSION_REQUIRED.unlink(missing_ok=True)
        (dirutil.RUNTIME / "assistant_error.json").unlink(missing_ok=True)
        return True
    except Exception as exc:
        message = str(exc)
        auth_failure = any(
            token in message.lower()
            for token in (
                "auth key",
                "unauthorized",
                "session revoked",
                "session expired",
                "user deactivated",
                "keyerror: 5",
            )
        )
        if auth_failure:
            dirutil.SESSION_REQUIRED.touch(exist_ok=True)
        _write_private_json(
            "assistant_error.json",
            {
                "ts": int(time.time()),
                "type": type(exc).__name__,
                "message": message[:500],
                "login_required": auth_failure,
            },
        )
        log.exception("Assistant startup failed; continuing in bot-only mode")
        try:
            await userbot.stop()
        except Exception:
            pass
        return False


async def _start_bot_with_backoff(assistant_ready: bool) -> None:
    """Start the bot once, sleeping in-process when Telegram requests it.

    Keeping the process alive prevents the one-minute watchdog from turning a
    single FLOOD_WAIT into repeated authorization attempts.
    """
    from pyrogram.errors import FloodWait

    while True:
        try:
            await bot.start()
            (dirutil.RUNTIME / "bot_start_error.json").unlink(missing_ok=True)
            return
        except FloodWait as exc:
            wait = max(1, int(getattr(exc, "value", 60))) + 3
            retry_at = int(time.time()) + wait
            payload = {
                "status": "rate_limited",
                "ts": int(time.time()),
                "pid": os.getpid(),
                "bot": f"@{config.BOT_USERNAME}",
                "assistant": f"@{config.ASSISTANT_USERNAME}",
                "assistant_ready": assistant_ready,
                "retry_after": wait,
                "retry_at": retry_at,
            }
            _write_private_json("bot_start_error.json", payload)
            _write_private_json("web_status.json", payload)
            log.warning("Telegram requested a %ss bot-start backoff; retrying in-process", wait)
            try:
                await bot.disconnect()
            except Exception:
                pass
            await asyncio.sleep(wait)


async def main() -> None:
    dirutil.ensure_dirs()
    setup_logging()

    problems = validate(require_assistant=False)
    if problems:
        for problem in problems:
            log.error("Configuration error: %s", problem)
        raise SystemExit(1)

    log.info("ShionMusicBot v%s booting", anony.__version__)
    db.load()

    assistant_ready = await _start_assistant()
    await _start_bot_with_backoff(assistant_ready)

    from anony import plugins as plugins_package

    plugin_count = len(list(pkgutil.iter_modules(plugins_package.__path__)))
    log.info("Loaded %d modules; assistant_ready=%s", plugin_count, assistant_ready)

    writer = asyncio.create_task(status_writer(assistant_ready))

    from pyrogram import idle

    await idle()

    log.info("Shutting down")
    writer.cancel()
    try:
        await writer
    except asyncio.CancelledError:
        pass

    if assistant_ready:
        try:
            await asyncio.wait_for(call.stop_all(), timeout=10)
        except Exception:
            pass
    db.save()
    for client, enabled in ((bot, True), (userbot, assistant_ready)):
        if not enabled:
            continue
        try:
            await client.stop()
        except Exception:
            pass
    await youtube.close()
    log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
