"""``/skip`` — jump to the next queued track."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, lang
from anony.helpers import admin_only, queue
from anony.helpers._player import advance

log = logging.getLogger(__name__)


@bot.on_message(filters.command("skip") & filters.group & admin_only)
@lang.language()
async def skip_command(client, message):
    chat_id = message.chat.id
    current = queue.getnow(chat_id)
    if current is None and not queue.get(chat_id):
        return await message.reply_text(await lang.t(chat_id, "nothing_playing"))

    title = current.title if current else "track"
    await advance(chat_id, ignore_loop=True)
    await message.reply_text(
        await lang.t(chat_id, "skipped", title=title)
    )
