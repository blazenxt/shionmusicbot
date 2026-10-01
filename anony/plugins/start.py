"""``/start``, ``/help`` and ``/settings`` handlers."""

from __future__ import annotations

import logging

from pyrogram import filters
from pyrogram.enums import ChatType

from anony import bot, db, lang
from anony.helpers import help_buttons, start_buttons, settings_buttons
from config import config

log = logging.getLogger(__name__)


@bot.on_message(filters.command("start") & filters.private)
@lang.language()
async def start_private(client, message):
    user = message.from_user
    if user is not None:
        await db.add_user(user.id)
    text = await lang.t(
        None,
        "start_private",
        user=user.first_name if user else "friend",
    )
    await message.reply_text(text, reply_markup=start_buttons())


@bot.on_message(filters.command("start") & filters.group)
@lang.language()
async def start_group(client, message):
    await db.add_chat(message.chat.id)
    await message.reply_text(
        await lang.t(message.chat.id, "start_group"),
        reply_markup=start_buttons(),
    )


@bot.on_message(filters.command("help"))
@lang.language()
async def help_command(client, message):
    await message.reply_text(
        await lang.t(message.chat.id, "help_text"),
        reply_markup=help_buttons(),
    )


@bot.on_message(filters.command("settings"))
@lang.language()
async def settings_command(client, message):
    chat_id = message.chat.id if message.chat else None
    code = await db.get_lang(chat_id)
    cmd_delete = await db.get_cmd_delete(chat_id) if chat_id else False
    await message.reply_text(
        await lang.t(chat_id, "settings_text"),
        reply_markup=settings_buttons(code, cmd_delete),
    )
