"""``/broadcast`` — owner announcement to every served chat."""

from __future__ import annotations

import asyncio
import logging

from pyrogram import filters
from pyrogram.errors import FloodWait

from anony import bot, db, lang
from anony.helpers import owner_only

log = logging.getLogger(__name__)


@bot.on_message(filters.command("broadcast") & owner_only)
@lang.language()
async def broadcast_command(client, message):
    target = getattr(message, "reply_to_message", None)
    if target is None:
        return await message.reply_text(await lang.t(None, "broadcast_usage"))

    chats = await db.get_chats()
    status = await message.reply_text(
        await lang.t(None, "broadcast_start", count=len(chats))
    )

    delivered = failed = 0
    for chat_id in chats:
        for attempt in (1, 2):
            try:
                await target.copy(chat_id)
                delivered += 1
                break
            except FloodWait as exc:
                if attempt == 1:
                    await asyncio.sleep(min(exc.value, 30))
                    continue
                failed += 1
            except Exception:  # noqa: BLE001 - unreachable / blocked chats
                failed += 1
                break
        await asyncio.sleep(0.1)

    try:
        await status.edit_text(
            await lang.t(None, "broadcast_done", ok=delivered, fail=failed)
        )
    except Exception:  # noqa: BLE001
        pass
