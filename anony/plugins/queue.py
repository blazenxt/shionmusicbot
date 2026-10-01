"""``/queue`` / ``/playlist`` — inspect or clear the chat queue."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, db, lang
from anony.helpers import is_privileged, queue

log = logging.getLogger(__name__)

_PAGE_SIZE = 10


async def build_queue_text(chat_id: int, page: int = 1) -> str:
    """Render the queue listing (used by /queue and the inline buttons)."""
    now = queue.getnow(chat_id)
    items = queue.get(chat_id)

    if now is None and not items:
        return await lang.t(chat_id, "queue_empty")

    lines = []
    if now is not None:
        lines.append(
            await lang.t(
                chat_id, "queue_now", title=now.title, duration=now.duration_text
            )
        )
    if items:
        lines.append("")
        total_pages = max(1, (len(items) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        page = max(1, min(page, total_pages))
        start = (page - 1) * _PAGE_SIZE
        for index, track in enumerate(items[start : start + _PAGE_SIZE], start + 1):
            lines.append(f"{index}. {track.summary()}")
        hidden = len(items) - (start + _PAGE_SIZE)
        if hidden > 0:
            lines.append(await lang.t(chat_id, "queue_more", n=hidden))

    return await lang.t(chat_id, "queue_title", count=len(items), entries="\n".join(lines))


@bot.on_message(filters.command(["queue", "playlist"]) & filters.group)
@lang.language()
async def queue_command(client, message):
    chat_id = message.chat.id
    text = (message.text or "").lower().split()

    if len(text) > 1 and text[1] in ("clear", "purge"):
        if not await is_privileged(message):
            return await message.reply_text(await lang.t(chat_id, "admin_only"))
        removed = queue.clear(chat_id)
        return await message.reply_text(
            await lang.t(chat_id, "queue_cleared", count=removed)
        )

    await message.reply_text(await build_queue_text(chat_id))
