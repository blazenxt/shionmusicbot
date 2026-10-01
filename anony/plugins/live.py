"""``/live`` and ``/vlive`` — resolve a live player page into VC media."""

from __future__ import annotations

import hashlib
import logging

from pyrogram import filters

from anony import bot, call, db, lang
from anony.core.live import LiveResolveError, resolve_live_url
from anony.helpers import Media, Track, admin_only, checkUB, extract_query, queue
from anony.helpers._inline import stream_controls

log = logging.getLogger(__name__)


@bot.on_message(filters.command(["live", "vlive"]) & filters.group & admin_only)
@checkUB
@lang.language()
async def live_command(client, message):
    chat_id = message.chat.id
    word = (message.command or ["live"])[0].split("@")[0].lower()
    video = word == "vlive"
    page_url = extract_query(message).strip()
    if not page_url:
        return await message.reply_text(
            await lang.t(chat_id, "live_usage", command=word)
        )

    status = await message.reply_text(await lang.t(chat_id, "live_resolving"))
    try:
        source = await resolve_live_url(page_url)
        await call.play(chat_id, source.url, video=video, headers=source.headers)
    except LiveResolveError as exc:
        log.info("Live page resolution rejected in %s: %s", chat_id, exc)
        return await status.edit_text(
            await lang.t(chat_id, "live_resolve_failed", error=str(exc))
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Live stream start failed in %s", chat_id)
        return await status.edit_text(
            await lang.t(chat_id, "live_start_failed", error=str(exc)[:180])
        )

    queue.clear(chat_id)
    await db.set_loop(chat_id, 0)
    user = getattr(message, "from_user", None)
    media = Media(
        video_id="live-" + hashlib.sha1(source.url.encode()).hexdigest()[:12],
        title=source.title,
        duration=0,
        duration_text="LIVE",
        stream_url=source.url,
        is_live=True,
    )
    track = Track(
        media=media,
        chat_id=chat_id,
        requester_id=user.id if user else None,
        requester_name=(user.first_name if user else None) or "Unknown",
        is_video=video,
    )
    queue.setnow(chat_id, track)
    await db.incr_counter("plays")
    await status.edit_text(
        await lang.t(
            chat_id,
            "live_started",
            title=source.title,
            mode="video" if video else "audio",
        ),
        reply_markup=stream_controls(chat_id),
    )
