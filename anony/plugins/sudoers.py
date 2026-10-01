"""``/addsudo`` / ``/delsudo`` / ``/sudolist`` — owner-level delegates."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, db, lang
from anony.helpers import owner_only
from config import config

log = logging.getLogger(__name__)


async def _target_user(client, message):
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
        except Exception:  # noqa: BLE001
            return None
    return None


def _mention(user) -> str:
    name = (user.first_name if getattr(user, "first_name", None) else None) or "User"
    uid = getattr(user, "id", 0)
    return f"[{name}](tg://user?id={uid})" if uid else name


@bot.on_message(filters.command("addsudo") & owner_only)
@lang.language()
async def addsudo_command(client, message):
    target = await _target_user(client, message)
    if target is None:
        return await message.reply_text(await lang.t(None, "auth_missing_user"))
    await db.add_admin(target.id)
    await message.reply_text(
        await lang.t(None, "sudo_added", user=_mention(target))
    )


@bot.on_message(filters.command("delsudo") & owner_only)
@lang.language()
async def delsudo_command(client, message):
    target = await _target_user(client, message)
    if target is None:
        return await message.reply_text(await lang.t(None, "auth_missing_user"))
    await db.del_admin(target.id)
    await message.reply_text(
        await lang.t(None, "sudo_removed", user=_mention(target))
    )


@bot.on_message(filters.command("sudolist") & owner_only)
@lang.language()
async def sudolist_command(client, message):
    ids = await db.get_admins()
    if not ids:
        return await message.reply_text(await lang.t(None, "sudo_list_empty"))
    entries = [
        f"{index}. [User](tg://user?id={uid}) — `{uid}`"
        for index, uid in enumerate(ids, 1)
        if uid != config.OWNER_ID
    ]
    entries.insert(0, f"👑 [Owner](tg://user?id={config.OWNER_ID}) — `{config.OWNER_ID}`")
    await message.reply_text(
        await lang.t(None, "sudo_list", users="\n".join(entries))
    )
