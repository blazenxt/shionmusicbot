"""``/auth`` / ``/unauth`` / ``/authusers`` — per-chat playback delegation."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, db, lang
from anony.helpers import admin_only

log = logging.getLogger(__name__)


def _mention(user) -> str:
    name = (user.first_name if getattr(user, "first_name", None) else None) or "User"
    uid = getattr(user, "id", 0)
    return f"[{name}](tg://user?id={uid})" if uid else name


async def _target_user(client, message):
    """Reply → that user; otherwise a numeric id or @username argument."""
    reply = getattr(message, "reply_to_message", None)
    if reply is not None and reply.from_user is not None:
        return reply.from_user

    args = (message.text or "").split()[1:]
    if args:
        token = args[0]
        try:
            if token.lstrip("-").isdigit():
                return await client.get_users(int(token))
            if token.startswith("@"):
                return await client.get_users(token)
        except Exception:  # noqa: BLE001 - unknown user
            return None
    return None


@bot.on_message(filters.command("auth") & filters.group & admin_only)
@lang.language()
async def auth_command(client, message):
    chat_id = message.chat.id
    target = await _target_user(client, message)
    if target is None:
        return await message.reply_text(await lang.t(chat_id, "auth_missing_user"))

    if await db.add_auth(chat_id, target.id):
        await message.reply_text(
            await lang.t(chat_id, "auth_added", user=_mention(target))
        )
    else:
        await message.reply_text(
            await lang.t(chat_id, "auth_exists", user=_mention(target))
        )


@bot.on_message(filters.command("unauth") & filters.group & admin_only)
@lang.language()
async def unauth_command(client, message):
    chat_id = message.chat.id
    target = await _target_user(client, message)
    if target is None:
        return await message.reply_text(await lang.t(chat_id, "auth_missing_user"))

    if await db.unauth(chat_id, target.id):
        await message.reply_text(
            await lang.t(chat_id, "auth_removed", user=_mention(target))
        )
    else:
        await message.reply_text(
            await lang.t(chat_id, "auth_not_present", user=_mention(target))
        )


@bot.on_message(filters.command("authusers") & filters.group)
@lang.language()
async def authusers_command(client, message):
    chat_id = message.chat.id
    ids = await db.get_auth(chat_id)
    if not ids:
        return await message.reply_text(await lang.t(chat_id, "auth_list_empty"))

    entries = []
    for index, uid in enumerate(ids, 1):
        entries.append(f"{index}. [User](tg://user?id={uid}) — `{uid}`")
    await message.reply_text(
        await lang.t(chat_id, "auth_list", users="\n".join(entries))
    )
