"""``/stats`` — live resource & playback metrics."""

from __future__ import annotations

import logging
import time

from pyrogram import filters

import anony
from anony import bot, call, db, lang
from anony.helpers import fmt_duration

log = logging.getLogger(__name__)

BOOT_TIME = getattr(anony, "BOOT_TIME", None) or time.time()


async def build_stats_text(chat_id=None) -> str:
    """Composed stats line used by /stats and the inline Stats button."""
    try:
        import pyrogram
        import pytgcalls

        versions = (
            pyrogram.__version__,
            pytgcalls.__version__,
        )
    except Exception:  # noqa: BLE001
        versions = ("?", "?")

    try:
        import psutil

        process = psutil.Process()
        mem = f"{process.memory_info().rss / 1_048_576:.0f} MB"
        cpu = f"{process.cpu_percent(interval=0.1):.0f}%"
    except Exception:  # noqa: BLE001
        mem = cpu = "n/a"

    dbstats = await db.stats()
    active = len(await call.active_chats())
    uptime = fmt_duration(int(time.time() - BOOT_TIME))

    import sys

    return await lang.t(
        chat_id,
        "stats_text",
        uptime=uptime,
        mem=mem,
        cpu=cpu,
        calls=active,
        chats=dbstats["chats"],
        users=dbstats["users"],
        plays=dbstats["plays"],
        py=sys.version.split()[0],
        pyrogram=versions[0],
        pytgcalls=versions[1],
    )


@bot.on_message(filters.command("stats"))
@lang.language()
async def stats_command(client, message):
    chat_id = message.chat.id if message.chat else None
    await message.reply_text(await build_stats_text(chat_id))
