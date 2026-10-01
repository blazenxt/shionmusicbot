"""Group membership events, command auto-delete and private fallbacks."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, db, lang
from anony.helpers import queue
from config import config

log = logging.getLogger(__name__)


# ── group membership events ────────────────────────────────────────────
@bot.on_message(filters.new_chat_members)
@lang.language()
async def new_members(client, message):
    chat_id = message.chat.id
    await db.add_chat(chat_id)
    for member in message.new_chat_members or []:
        if member is None:
            continue
        if getattr(member, "is_self", False):
            return await message.reply_text(
                await lang.t(
                    chat_id,
                    "start_group_added",
                    chat=message.chat.title or "the group",
                    assistant=f"@{config.ASSISTANT_USERNAME}",
                )
            )
        if member.id == config.ASSISTANT_ID:
            return await message.reply_text(await lang.t(chat_id, "assistant_joined"))


@bot.on_message(filters.left_chat_member)
async def left_member(client, message):
    member = message.left_chat_member
    if member is not None and getattr(member, "is_self", False):
        chat_id = message.chat.id
        await db.rm_chat(chat_id)
        queue.clear_all(chat_id)


# ── command auto-delete (runs before all handlers, group -1) ───────────
@bot.on_message(filters.group & filters.regex(r"^/"), group=-1)
async def cmd_autodelete(client, message):
    try:
        if await db.get_cmd_delete(message.chat.id):
            await message.delete()
    except Exception:  # noqa: BLE001 - deletion needs admin rights
        pass


# ── private fallbacks ──────────────────────────────────────────────────
# misc.py loads before several command modules. A broad /^\// handler here
# would therefore consume valid commands (including /start) before their real
# handlers are reached. Keep a complete command registry so this fallback only
# catches genuinely unknown commands.
KNOWN_COMMANDS = [
    "start", "help", "settings", "id", "lang", "ping", "alive", "stats",
    "auth", "unauth", "authusers", "blacklistchat", "whitelistchat",
    "blacklistedchats", "broadcast", "loop", "pause", "play", "vplay",
    "playforce", "vplayforce", "queue", "playlist", "resume", "seek",
    "shuffle", "skip", "stop", "end", "addsudo", "delsudo", "sudolist",
    "restart", "logs", "exec", "volume",
]
GROUP_ONLY_COMMANDS = [
    "auth", "unauth", "authusers", "loop", "pause", "play", "vplay",
    "playforce", "vplayforce", "queue", "playlist", "resume", "seek",
    "shuffle", "skip", "stop", "end", "volume",
]


@bot.on_message(filters.private & filters.command(GROUP_ONLY_COMMANDS))
@lang.language()
async def private_group_command(client, message):
    """Explain where voice-chat-only commands can be used."""
    await message.reply_text(await lang.t(None, "private_hint"))


@bot.on_message(
    filters.private
    & filters.text
    & filters.regex(r"^/")
    & ~filters.command(KNOWN_COMMANDS)
)
@lang.language()
async def unknown_command(client, message):
    await message.reply_text(await lang.t(None, "no_command"))


@bot.on_message(filters.private & filters.text & ~filters.regex(r"^/"))
@lang.language()
async def private_text(client, message):
    user = getattr(message, "from_user", None)
    if user is not None:
        await db.add_user(user.id)
    await message.reply_text(await lang.t(None, "private_hint"))
