"""Queue orchestration — the playback heart of the bot.

``start_stream``   pipes a track into the voice chat (refreshing the
                    short-lived Testweb3 stream token first, with a
                    download-to-disk fallback).
``on_stream_end``  PyTgCalls hook: honours ``/loop``, advances the queue,
                    schedules the idle auto-leave.
``advance``        manual skip-equivalent used by /skip & callbacks.
``stop_and_clear`` full stop (queue + playing track + call).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

from anony.core.youtube import youtube
from anony.helpers._queue import queue
from config import config

log = logging.getLogger(__name__)

# last advance timestamp per chat — debounces the paired audio+video
# stream-end events emitted for one finished track
_advancing: Dict[int, float] = {}
_idle_tasks: Dict[int, asyncio.Task] = {}

_DEBOUNCE = 4.0
IDLE_GRACE = 120  # seconds to idle in the voice chat before leaving


async def start_stream(chat_id: int, track, announce: bool = True) -> None:
    """Begin (or seamlessly switch to) ``track`` in ``chat_id``."""
    from anony import bot, call, db, lang
    from anony.helpers._inline import stream_controls

    # Stream tokens are short lived — always resolve a fresh one.
    url = track.media.stream_url
    try:
        info = await youtube.refresh_stream(track.media.video_id)
    except Exception:  # noqa: BLE001 - refresh is best effort
        info = None
    if info:
        if info.get("stream_url"):
            url = track.media.stream_url = info["stream_url"]
        if info.get("title"):
            track.media.title = info["title"]
        if info.get("duration_text"):
            track.media.duration_text = info["duration_text"]
    if not url:
        raise RuntimeError("no stream URL available")

    try:
        await call.play(chat_id, url, video=track.is_video)
    except Exception as exc:  # noqa: BLE001 - fall back to local file
        log.warning("Direct piping failed (%s); downloading instead…", exc)
        path = await _download(url, track)
        await call.play(chat_id, path, video=track.is_video)

    queue.setnow(chat_id, track)
    await db.incr_counter("plays")
    _cancel_idle(chat_id)

    if announce:
        try:
            text = await lang.t(
                chat_id,
                "now_playing",
                title=track.media.title,
                duration=track.media.duration_text,
                user=track.requester_name,
                mode="🎬" if track.is_video else "🎵",
            )
            markup = stream_controls(chat_id)
            thumb = None
            try:
                from anony.helpers._thumbnails import fetch_thumbnail

                thumb = await asyncio.wait_for(
                    fetch_thumbnail(track.media), timeout=10
                )
            except Exception:  # noqa: BLE001 - thumbnails are decorative
                thumb = None
            if thumb:
                await bot.send_photo(
                    chat_id, thumb, caption=text, reply_markup=markup
                )
            else:
                await bot.send_message(chat_id, text, reply_markup=markup)
        except Exception:  # noqa: BLE001 - announcements are best effort
            pass


async def _download(url: str, track) -> str:
    """Download the stream to ``downloads/`` as a playback fallback."""
    import os

    from anony.core.dir import DOWNLOADS

    path = DOWNLOADS / f"{track.media.video_id}.mp3"
    if path.exists() and path.stat().st_size > 10_000:
        return str(path)

    from anony.core.youtube import youtube

    session = await youtube.session()
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".part"
    async with session.get(url) as response:
        response.raise_for_status()
        with open(tmp, "wb") as fh:
            async for chunk in response.content.iter_chunked(1 << 16):
                fh.write(chunk)
    os.replace(tmp, path)
    return str(path)


async def on_stream_end(chat_id: int) -> None:
    """PyTgCalls stream-end hook with loop support and queue advance."""
    now = time.monotonic()
    if now - _advancing.get(chat_id, 0.0) < _DEBOUNCE:
        return  # second (video) end event of the same track
    _advancing[chat_id] = now
    await advance(chat_id)


async def advance(chat_id: int, ignore_loop: bool = False) -> None:
    """Loop the current track or move to the next one; leave when idle."""
    from anony import call, db

    if not ignore_loop:
        loop_count = await db.get_loop(chat_id)
        current = queue.getnow(chat_id)
        if current is not None and loop_count > 0:
            if loop_count > 1:
                await db.set_loop(chat_id, loop_count - 1)
            try:
                log.info("Looping '%s' in %s (%d left)", current.title, chat_id, loop_count)
                await start_stream(chat_id, current)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("Loop replay failed: %s", exc)

    # walk the queue until one track actually starts
    while True:
        nxt = queue.pop(chat_id)
        if nxt is None:
            break
        try:
            await start_stream(chat_id, nxt)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping '%s' after error: %s", nxt.title, exc)

    # nothing left to play
    queue.setnow(chat_id, None)
    await db.set_loop(chat_id, 0)
    _schedule_idle_leave(chat_id)


def _cancel_idle(chat_id: int) -> None:
    task = _idle_tasks.pop(chat_id, None)
    if task is not None and not task.done():
        task.cancel()


def _schedule_idle_leave(chat_id: int) -> None:
    _cancel_idle(chat_id)

    async def _leave() -> None:
        try:
            await asyncio.sleep(3 if config.AUTO_END else IDLE_GRACE)
        except asyncio.CancelledError:
            return
        if queue.getnow(chat_id) is None:
            from anony import call

            log.info("Voice chat idle in %s — leaving.", chat_id)
            await call.stop(chat_id)

    _idle_tasks[chat_id] = asyncio.create_task(_leave())


async def stop_and_clear(chat_id: int) -> None:
    """Full stop: playing track, queue, loop state and the group call."""
    from anony import call, db

    queue.clear_all(chat_id)
    await db.set_loop(chat_id, 0)
    _cancel_idle(chat_id)
    await call.stop(chat_id)
