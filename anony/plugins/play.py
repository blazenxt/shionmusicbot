"""``/play``, ``/vplay``, ``/playforce``, ``/vplayforce`` — the Testweb3 engine.

Flow
----
1. ``checkUB`` validates group / blacklist / queue limit / assistant.
2. Resolve the track: YouTube link → video id, otherwise Testweb3 search.
3. Enforce the duration limit (privileged users bypass).
4. Start streaming immediately when idle, else append to the queue.
"""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, db, lang
from anony.core.youtube import video_id_from_url, youtube
from anony.helpers import (
    Media,
    Track,
    checkUB,
    extract_query,
    get_urls,
    is_privileged,
    queue,
    truncate,
)
from anony.helpers._player import start_stream
from anony.helpers._utilities import play_log
from config import config

log = logging.getLogger(__name__)


def _command_word(message) -> str:
    """Return the bare command word ('play', 'vplayforce', …)."""
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    if not text:
        return "play"
    return text.split()[0].lstrip("/").split("@")[0].lower()


async def resolve_media(query: str):
    """Resolve a query (link or plain text) into a :class:`Media`."""
    video_id = None
    if get_urls(query):
        video_id = video_id_from_url(query)
    if video_id is None:
        results = await youtube.search(query, limit=1)
        if not results:
            return None
        video_id = results[0]["id"]

    info = await youtube.video(video_id)
    if info is None or not info.get("stream_url"):
        return None
    return Media.from_info(info)


@bot.on_message(
    filters.command(["play", "vplay", "playforce", "vplayforce"]) & filters.group
)
@checkUB
@lang.language()
async def play_command(client, message):
    chat_id = message.chat.id
    word = _command_word(message)
    is_video = word in ("vplay", "vplayforce")
    is_force = word in ("playforce", "vplayforce")

    if is_video and not config.VIDEO_PLAY:
        return await message.reply_text(await lang.t(chat_id, "video_disabled"))

    query = extract_query(message)
    if not query:
        return await message.reply_text(
            await lang.t(chat_id, "play_usage", command=word.split("force")[0])
        )

    status = await message.reply_text(
        await lang.t(chat_id, "searching", query=truncate(query, 60))
    )

    try:
        media = await resolve_media(query)
    except Exception:  # noqa: BLE001
        log.exception("Track resolution failed")
        media = None

    if media is None:
        try:
            return await status.edit_text(
                await lang.t(chat_id, "not_found", query=truncate(query, 60))
            )
        except Exception:  # noqa: BLE001
            return None
    if media.is_live:
        try:
            return await status.edit_text(await lang.t(chat_id, "live_stream"))
        except Exception:  # noqa: BLE001
            return None

    privileged = await is_privileged(message)
    if media.duration > config.duration_limit_secs and not privileged:
        try:
            return await status.edit_text(
                await lang.t(
                    chat_id,
                    "duration_limit",
                    title=media.title,
                    duration=media.duration_text,
                    limit=config.DURATION_LIMIT,
                )
            )
        except Exception:  # noqa: BLE001
            return None

    user = getattr(message, "from_user", None)
    track = Track(
        media=media,
        chat_id=chat_id,
        requester_id=user.id if user else None,
        requester_name=(user.first_name if user else None) or "Unknown",
        is_video=is_video,
    )
    play_log(chat_id, user, track)

    async def drop_status() -> None:
        try:
            await status.delete()
        except Exception:  # noqa: BLE001
            pass

    # ── force play: clear queue, switch source immediately ─────────
    if is_force:
        queue.clear(chat_id)
        await db.set_loop(chat_id, 0)
        try:
            await start_stream(chat_id, track)
            await drop_status()
        except Exception as exc:  # noqa: BLE001
            log.exception("Force play failed")
            try:
                await status.edit_text(
                    await lang.t(chat_id, "fetch_failed") + f"\n`{exc}`"
                )
            except Exception:  # noqa: BLE001
                pass
        return

    # ── idle chat → start instantly ────────────────────────────────
    if queue.getnow(chat_id) is None:
        try:
            await start_stream(chat_id, track)
            await drop_status()
        except Exception:  # noqa: BLE001
            log.exception("Stream start failed")
            try:
                await status.edit_text(await lang.t(chat_id, "fetch_failed"))
            except Exception:  # noqa: BLE001
                pass
        return

    # ── already streaming → append to queue ────────────────────────
    position = queue.put(chat_id, track)
    try:
        await status.edit_text(
            await lang.t(
                chat_id,
                "added_queue",
                title=media.title,
                duration=media.duration_text,
                user=track.requester_name,
                position=position,
            )
        )
    except Exception:  # noqa: BLE001
        pass
