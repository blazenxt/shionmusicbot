"""``/id`` — chat / user identity."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, lang

log = logging.getLogger(__name__)


@bot.on_message(filters.command("id"))
@lang.language()
async def id_command(client, message):
    user = getattr(message, "from_user", None)
    sender = getattr(message, "sender_chat", None)
    user_label = user.id if user else (sender.id if sender else "?")
    await message.reply_text(
        await lang.t(message.chat.id, "id_text", chat=message.chat.id, user=user_label)
    )
