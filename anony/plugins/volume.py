"""``/volume`` — change the stream volume without clipping (0-100)."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, call, lang
from anony.helpers import admin_only

log = logging.getLogger(__name__)


@bot.on_message(filters.command("volume") & filters.group & admin_only)
@lang.language()
async def volume_command(client, message):
    chat_id = message.chat.id
    args = (message.text or "").split()[1:]

    # Values above 100 amplify already-normalised PCM and audibly clip on
    # Telegram (the reported "kat-kat" distortion). Keep the public control
    # in the clean, lossless range.
    if not args or not args[0].isdigit() or not 0 <= int(args[0]) <= 100:
        return await message.reply_text(await lang.t(chat_id, "volume_usage"))

    volume = int(args[0])
    try:
        await call.app.change_volume_call(chat_id, volume)
    except Exception as exc:  # noqa: BLE001 - NotInCallError etc.
        log.warning("volume change failed in %s: %s", chat_id, exc)
        return await message.reply_text(await lang.t(chat_id, "nothing_playing"))

    await message.reply_text(await lang.t(chat_id, "volume_set", vol=volume))
