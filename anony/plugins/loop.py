"""``/loop`` — repeat the current track n times (or off)."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, db, lang
from anony.helpers import admin_only

log = logging.getLogger(__name__)

MAX_LOOP = 10


@bot.on_message(filters.command("loop") & filters.group & admin_only)
@lang.language()
async def loop_command(client, message):
    chat_id = message.chat.id
    args = (message.text or "").split()[1:]

    if not args:
        current = await db.get_loop(chat_id)
        status = f"ON × {current}" if current > 0 else "OFF"
        return await message.reply_text(
            await lang.t(chat_id, "loop_status", status=status)
        )

    arg = args[0].lower()
    if arg in ("off", "0"):
        await db.set_loop(chat_id, 0)
        return await message.reply_text(await lang.t(chat_id, "loop_off"))

    if arg.isdigit():
        count = max(1, min(int(arg), MAX_LOOP))
        await db.set_loop(chat_id, count)
        return await message.reply_text(
            await lang.t(chat_id, "loop_set", n=count)
        )

    await message.reply_text(await lang.t(chat_id, "loop_invalid"))
