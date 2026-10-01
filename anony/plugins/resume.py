"""``/resume`` — resume a paused stream."""

from __future__ import annotations

import logging

from pyrogram import filters
from pytgcalls.exceptions import NotInCallError

from anony import bot, call, lang
from anony.helpers import admin_only

log = logging.getLogger(__name__)


@bot.on_message(filters.command("resume") & filters.group & admin_only)
@lang.language()
async def resume_command(client, message):
    chat_id = message.chat.id
    try:
        await call.resume(chat_id)
    except NotInCallError:
        return await message.reply_text(await lang.t(chat_id, "nothing_playing"))
    except Exception as exc:  # noqa: BLE001
        log.warning("resume failed in %s: %s", chat_id, exc)
        return await message.reply_text(await lang.t(chat_id, "error"))
    await message.reply_text(await lang.t(chat_id, "resumed"))
