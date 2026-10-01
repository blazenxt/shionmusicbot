"""``/lang`` — per-chat language switcher."""

from __future__ import annotations

import logging

from pyrogram import filters
from pyrogram.enums import ChatType

from anony import bot, db, lang
from anony.helpers import is_privileged

log = logging.getLogger(__name__)


@bot.on_message(filters.command("lang"))
@lang.language()
async def lang_command(client, message):
    chat = message.chat
    args = (message.text or "").split()[1:]

    if chat is not None and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await is_privileged(message):
            return await message.reply_text(await lang.t(chat.id, "admin_only"))
    if not args or args[0].lower() not in lang.codes():
        codes = " / ".join(lang.codes())
        return await message.reply_text(f"💡 Usage: /lang <{codes}>")

    code = args[0].lower()
    await db.set_lang(chat.id, code)
    await message.reply_text(
        await lang.t(chat.id, "settings_lang_set", lang=code.upper())
    )
