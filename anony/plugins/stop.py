"""``/stop`` / ``/end`` — stop playback and clear the queue."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, lang
from anony.helpers import admin_only
from anony.helpers._player import stop_and_clear

log = logging.getLogger(__name__)


@bot.on_message(filters.command(["stop", "end"]) & filters.group & admin_only)
@lang.language()
async def stop_command(client, message):
    chat_id = message.chat.id
    await stop_and_clear(chat_id)
    await message.reply_text(await lang.t(chat_id, "stopped"))
