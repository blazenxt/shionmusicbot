"""``checkUB`` — pre-flight validation decorator for playback commands.

Validates, in order:

1. the update happened in a group / supergroup,
2. the chat is not blacklisted,
3. the sender is a real user (or an anonymous group admin),
4. the queue limit is respected (privileged users bypass it),
5. the assistant account is a member of the chat (auto-join attempt via
   an invite link when the bot may export one).
"""

from __future__ import annotations

import functools
import logging

from pyrogram.enums import ChatMemberStatus, ChatType

from config import config

log = logging.getLogger(__name__)


async def assistant_in_chat(chat_id: int) -> bool:
    """True when @<ASSISTANT_USERNAME> is a member of ``chat_id``."""
    from anony import userbot

    if not config.ASSISTANT_ID or not config.assistant_session:
        return True  # cannot verify — let PyTgCalls decide later

    try:
        member = await userbot.get_chat_member(chat_id, config.ASSISTANT_ID)
        return member is not None and member.status not in (
            ChatMemberStatus.LEFT,
            ChatMemberStatus.BANNED,
        )
    except Exception:  # noqa: BLE001 - not a member, chat error, …
        return False


async def try_join_assistant(client, chat_id: int) -> bool:
    """Try to pull the assistant in via a bot-exported invite link."""
    from anony import userbot

    try:
        link = await client.export_chat_invite_link(chat_id)
        await userbot.join_chat(link)
    except Exception as exc:  # noqa: BLE001 - no admin rights, ban, …
        log.info("Assistant auto-join failed for %s: %s", chat_id, exc)
        return False
    return await assistant_in_chat(chat_id)


def checkUB(func):
    """Wrap a playback handler with all pre-flight checks."""

    @functools.wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        from anony import db, lang
        from anony.helpers._admins import is_privileged
        from anony.helpers._queue import queue

        chat = getattr(message, "chat", None)
        if chat is None or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                await message.reply_text(
                    await lang.t(None, "only_group"),
                )
            except Exception:  # noqa: BLE001
                pass
            return

        chat_id = chat.id

        if await db.is_blacklisted(chat_id):
            return  # silently ignore blacklisted chats

        await db.add_chat(chat_id)

        user = getattr(message, "from_user", None)
        if user is None:
            # Channel posts / anonymous admins: allow only the group itself.
            sender_chat = getattr(message, "sender_chat", None)
            if not (sender_chat is not None and sender_chat.id == chat_id):
                return

        privileged = await is_privileged(message)

        if (
            not privileged
            and queue.size(chat_id) >= config.QUEUE_LIMIT
        ):
            try:
                await message.reply_text(
                    await lang.t(chat_id, "queue_full", limit=config.QUEUE_LIMIT)
                )
            except Exception:  # noqa: BLE001
                pass
            return

        if not await assistant_in_chat(chat_id):
            joined = await try_join_assistant(client, chat_id)
            if not joined:
                try:
                    await message.reply_text(
                        await lang.t(
                            chat_id,
                            "assistant_missing",
                            assistant=f"@{config.ASSISTANT_USERNAME}",
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass
                return

        return await func(client, message, *args, **kwargs)

    return wrapper
