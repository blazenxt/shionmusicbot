"""Owner-only maintenance tools: ``/restart``, ``/logs``, ``/exec``."""

from __future__ import annotations

import logging
import os
import sys

from pyrogram import filters

import anony
from anony import bot, db, lang
from anony.core.dir import LOG_FILE
from anony.helpers import aexec, owner_only
from config import config

log = logging.getLogger(__name__)


@bot.on_message(filters.command("restart") & owner_only)
@lang.language()
async def restart_command(client, message):
    await message.reply_text(await lang.t(None, "restarting"))
    db.save()
    os.execv(sys.executable, [sys.executable, "-m", "anony"])


@bot.on_message(filters.command("logs") & owner_only)
@lang.language()
async def logs_command(client, message):
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-30:]
    except OSError:
        return await message.reply_text("📜 No log file yet.")
    text = "".join(lines) or "📜 Log file is empty."
    await message.reply_text(f"```\n{text[-3500:]}\n```")


@bot.on_message(filters.command("exec") & owner_only)
@lang.language()
async def exec_command(client, message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("💡 Usage: /exec <python code>")

    environment = {
        "client": client,
        "message": message,
        "bot": bot,
        "db": db,
        "lang": lang,
        "config": config,
        "anony": anony,
    }
    try:
        result = await aexec(parts[1], environment)
        output = repr(result) if result is not None else "✅ OK"
    except Exception as exc:  # noqa: BLE001 - the point is showing errors
        output = f"❌ {type(exc).__name__}: {exc}"
    await message.reply_text(f"```\n{output[:3500]}\n```")
