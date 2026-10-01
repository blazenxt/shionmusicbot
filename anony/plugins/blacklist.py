"""``/blacklistchat`` / ``/whitelistchat`` / ``/blacklistedchats`` — sudo only."""

from __future__ import annotations

import logging

from pyrogram import filters
from pyrogram.enums import ChatType

from anony import bot, db, lang
from anony.helpers import queue, sudo_only

log = logging.getLogger(__name__)


def _chat_argument(message):
    args = (message.text or "").split()[1:]
    if args and args[0].lstrip("-").isdigit():
        return int(args[0])
    chat = getattr(message, "chat", None)
    if chat is not None and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        return chat.id
    return None


@bot.on_message(filters.command("blacklistchat") & sudo_only)
@lang.language()
async def blacklistchat_command(client, message):
    chat_id = _chat_argument(message)
    if chat_id is None:
        return await message.reply_text(await lang.t(None, "bl_usage"))

    await db.blacklist_chat(chat_id)
    queue.clear_all(chat_id)

    chat = getattr(message, "chat", None)
    if chat is not None and chat.id == chat_id and chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ):
        try:
            await message.reply_text(await lang.t(chat_id, "bl_added", chat=chat_id))
            await client.leave_chat(chat_id)
            return None
        except Exception:  # noqa: BLE001 - leaving is best effort
            pass
    await message.reply_text(await lang.t(None, "bl_added", chat=chat_id))


@bot.on_message(filters.command("whitelistchat") & sudo_only)
@lang.language()
async def whitelistchat_command(client, message):
    chat_id = _chat_argument(message)
    if chat_id is None:
        return await message.reply_text(await lang.t(None, "bl_usage"))

    if chat_id in await db.get_blacklisted_chats():
        await db.whitelist_chat(chat_id)
        await message.reply_text(await lang.t(None, "bl_removed", chat=chat_id))
    else:
        await message.reply_text(await lang.t(None, "bl_not_listed", chat=chat_id))


@bot.on_message(filters.command("blacklistedchats") & sudo_only)
@lang.language()
async def blacklisted_command(client, message):
    chats = await db.get_blacklisted_chats()
    if not chats:
        return await message.reply_text(await lang.t(None, "bl_list_empty"))
    listing = "\n".join(f"• `{chat_id}`" for chat_id in chats)
    await message.reply_text(await lang.t(None, "bl_list", chats=listing))
