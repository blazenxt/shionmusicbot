"""``/ping`` / ``/alive`` — latency, uptime and PyTgCalls health."""

from __future__ import annotations

import time

from pyrogram import filters

import anony
from anony import bot, call, lang
from anony.helpers import fmt_duration

BOOT_TIME = getattr(anony, "BOOT_TIME", None) or time.time()


@bot.on_message(filters.command(["ping", "alive"]))
@lang.language()
async def ping_command(client, message):
    chat_id = message.chat.id if message.chat else None
    start = time.perf_counter()
    pong = await message.reply_text("…")
    latency = round((time.perf_counter() - start) * 1000)

    uptime = fmt_duration(int(time.time() - BOOT_TIME))
    active = len(await call.active_chats())
    text = await lang.t(
        chat_id,
        "ping_text",
        latency=latency,
        uptime=uptime,
        calls=active,
        tgcalls=round(call.ping(), 1),
    )
    try:
        await pong.edit_text(text)
    except Exception:  # noqa: BLE001 - fall back to a fresh reply
        await message.reply_text(text)
