"""Admin / privilege checks with a short-lived cache.

Privilege hierarchy used across the bot:

* **owner / sudo** — ``config.OWNER_ID`` plus users added with ``/addsudo``
* **chat admin** — Telegram administrators of the chat (incl. anonymous
  admins posting as the group itself)
* **auth user** — per-chat users promoted with ``/auth``

``is_privileged`` accepts any of the three; ``admin_only`` /
``sudo_only`` / ``owner_only`` are ready-made Pyrogram filters.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus

from config import config

_CACHE_TTL = 300  # seconds
_cache: Dict[Tuple[int, int], Tuple[bool, float]] = {}

_ACTIVE_STATUSES = {
    ChatMemberStatus.OWNER,
    ChatMemberStatus.ADMINISTRATOR,
}


def _cache_get(chat_id: int, user_id: int) -> Optional[bool]:
    entry = _cache.get((chat_id, user_id))
    if entry is None:
        return None
    verdict, stamp = entry
    if time.monotonic() - stamp > _CACHE_TTL:
        _cache.pop((chat_id, user_id), None)
        return None
    return verdict


def _cache_put(chat_id: int, user_id: int, verdict: bool) -> None:
    if len(_cache) > 4096:
        _cache.clear()
    _cache[(chat_id, user_id)] = (verdict, time.monotonic())


async def is_admin(chat_id: int, user_id: Optional[int]) -> bool:
    """True when ``user_id`` administers ``chat_id`` (sudo included)."""
    if user_id is None:
        return False
    from anony import db

    if await db.is_sudo(user_id):
        return True
    if user_id in (777000, 1087968824):  # Telegram service / GroupAnonymousBot
        return bool(chat_id and user_id in (1087968824,) and False)

    cached = _cache_get(chat_id, user_id)
    if cached is not None:
        return cached

    verdict = False
    try:
        from anony import bot

        member = await bot.get_chat_member(chat_id, user_id)
        verdict = member is not None and member.status in _ACTIVE_STATUSES
    except Exception:  # noqa: BLE001 - chat not found, user kicked, …
        verdict = False
    _cache_put(chat_id, user_id, verdict)
    return verdict


async def is_privileged(message) -> bool:
    """Admin / sudo / auth-user / anonymous-admin check for a message."""
    user = getattr(message, "from_user", None)
    chat = getattr(message, "chat", None)
    if chat is None:
        return False

    from anony import db

    if user is not None and await db.is_sudo(user.id):
        return True

    # Anonymous admins post as the chat itself.
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat is not None and sender_chat.id == chat.id:
        return True

    if user is None:
        return False

    if await is_admin(chat.id, user.id):
        return True
    return await db.is_auth(chat.id, user.id)


# ── ready-made Pyrogram filters ────────────────────────────────────────
async def _admin_filter(_, __, message) -> bool:
    return await is_privileged(message)


async def _sudo_filter(_, __, message) -> bool:
    user = getattr(message, "from_user", None)
    if user is None:
        sender_chat = getattr(message, "sender_chat", None)
        if sender_chat is not None and getattr(message.chat, "id", None) == sender_chat.id:
            return True
        return False
    from anony import db

    return await db.is_sudo(user.id)


async def _owner_filter(_, __, message) -> bool:
    user = getattr(message, "from_user", None)
    return user is not None and user.id == config.OWNER_ID


admin_only = filters.create(_admin_filter)
sudo_only = filters.create(_sudo_filter)
owner_only = filters.create(_owner_filter)
