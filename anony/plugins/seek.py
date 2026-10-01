"""``/seek`` — jump to a position inside the current track.

Implemented by re-piping the stream with an ffmpeg ``-ss`` offset
(PyTgCalls swaps the source seamlessly on an active call).
"""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, call, lang
from anony.helpers import admin_only, fmt_duration, parse_duration, queue

log = logging.getLogger(__name__)


@bot.on_message(filters.command("seek") & filters.group & admin_only)
@lang.language()
async def seek_command(client, message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        return await message.reply_text(await lang.t(chat_id, "seek_usage"))

    seconds = parse_duration(parts[1].strip())
    if seconds <= 0:
        return await message.reply_text(await lang.t(chat_id, "seek_usage"))

    current = queue.getnow(chat_id)
    if current is None or not current.media.stream_url:
        return await message.reply_text(await lang.t(chat_id, "seek_failed"))

    try:
        await call.play(
            chat_id,
            current.media.stream_url,
            video=current.is_video,
            seek=seconds,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("seek failed in %s: %s", chat_id, exc)
        return await message.reply_text(await lang.t(chat_id, "seek_failed"))

    await message.reply_text(
        await lang.t(chat_id, "seek_done", position=fmt_duration(seconds))
    )
