from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable

from pyrogram.enums import ChatMemberStatus, ChatType

from .clients import CONFIG, db
from .strings import NEED_ADMIN, NEED_GROUP

Handler = Callable[..., Awaitable[Any]]


def touch_chat_later(message) -> None:
    try:
        asyncio.create_task(db.touch_chat(message.chat.id, getattr(message.chat, "title", None)))
    except Exception:
        pass


def is_group_message(message) -> bool:
    return getattr(message.chat, "type", None) in {ChatType.GROUP, ChatType.SUPERGROUP}


async def is_user_admin(client, chat_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    if CONFIG.sudo_users and user_id in CONFIG.sudo_users:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    status = getattr(member, "status", None)
    if status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}:
        return True
    status_text = str(status).lower()
    return any(part in status_text for part in ("owner", "creator", "administrator", "admin"))


async def is_authorized_user(client, chat_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    if await is_user_admin(client, chat_id, user_id):
        return True
    return await db.is_auth_user(chat_id, user_id)


def group_only(func: Handler) -> Handler:
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        if not is_group_message(message):
            return await message.reply_text(NEED_GROUP)
        touch_chat_later(message)
        return await func(client, message, *args, **kwargs)

    return wrapper


def admin_or_auth(func: Handler) -> Handler:
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        if not is_group_message(message):
            return await message.reply_text(NEED_GROUP)
        touch_chat_later(message)
        user = getattr(message, "from_user", None)
        user_id = getattr(user, "id", None)
        if await is_authorized_user(client, message.chat.id, user_id):
            return await func(client, message, *args, **kwargs)
        return await message.reply_text(NEED_ADMIN)

    return wrapper


def sudo_only(func: Handler) -> Handler:
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        user = getattr(message, "from_user", None)
        user_id = getattr(user, "id", None)
        if CONFIG.sudo_users and user_id in CONFIG.sudo_users:
            return await func(client, message, *args, **kwargs)
        return await message.reply_text("Owner-only command.")

    return wrapper
