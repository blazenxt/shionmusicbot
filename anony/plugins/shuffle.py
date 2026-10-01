"""``/shuffle`` — randomise the queued tracks."""

from __future__ import annotations

import logging
import random

from pyrogram import filters

from anony import bot, lang
from anony.helpers import admin_only, queue

log = logging.getLogger(__name__)


@bot.on_message(filters.command("shuffle") & filters.group & admin_only)
@lang.language()
async def shuffle_command(client, message):
    chat_id = message.chat.id
    items = queue.get(chat_id)
    if len(items) < 2:
        return await message.reply_text(await lang.t(chat_id, "queue_empty"))

    random.shuffle(items)
    queue.replace(chat_id, items)
    await message.reply_text(
        await lang.t(chat_id, "queue_shuffled", count=len(items))
    )
