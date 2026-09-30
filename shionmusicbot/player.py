from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pytgcalls import filters as call_filters
from pytgcalls.types import AudioQuality, GroupCallConfig, MediaStream, StreamEnded

from .models import Track
from .utils import format_duration, html_user, split_text

logger = logging.getLogger(__name__)


class LoopMode:
    OFF = "off"
    ONE = "one"
    QUEUE = "queue"

    ALL = {OFF, ONE, QUEUE}


@dataclass(slots=True)
class QueueState:
    queue: Deque[Track] = field(default_factory=deque)
    current: Track | None = None
    paused: bool = False
    loop: str = LoopMode.OFF
    volume: int = 100
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    suppress_end_until: float = 0.0


@dataclass(slots=True)
class EnqueueResult:
    started: bool
    position: int
    track: Track


class Player:
    def __init__(self, bot, calls, database, config) -> None:
        self.bot = bot
        self.calls = calls
        self.database = database
        self.config = config
        self._states: dict[int, QueueState] = {}
        self._handlers_registered = False

    def state(self, chat_id: int) -> QueueState:
        if chat_id not in self._states:
            self._states[chat_id] = QueueState()
        return self._states[chat_id]

    def register_call_handlers(self) -> None:
        if self._handlers_registered:
            return

        @self.calls.on_update(call_filters.stream_end(StreamEnded.Type.AUDIO))
        async def _stream_end_handler(_, update: StreamEnded) -> None:
            await self.on_stream_end(update.chat_id)

        self._handlers_registered = True

    async def add_track(self, chat_id: int, track: Track, *, force: bool = False) -> EnqueueResult:
        state = self.state(chat_id)
        should_start = False
        async with state.lock:
            if force:
                await self._cleanup_queue(state)
                await self._cleanup_current(state)
                state.queue.clear()
                state.current = track
                state.paused = False
                state.suppress_end_until = time.monotonic() + 4
                should_start = True
                position = 0
            elif state.current is None:
                state.current = track
                state.paused = False
                should_start = True
                position = 0
            else:
                state.queue.append(track)
                position = len(state.queue)

        if should_start:
            try:
                await self._play_track(chat_id, track)
            except Exception:
                async with state.lock:
                    if state.current is track:
                        state.current = None
                        state.paused = False
                await self._cleanup_track(track)
                try:
                    await self.calls.leave_call(chat_id)
                except Exception:
                    pass
                raise
        return EnqueueResult(started=should_start, position=position, track=track)

    async def add_many(self, chat_id: int, tracks: list[Track]) -> tuple[int, bool]:
        if not tracks:
            return 0, False
        started = False
        first = True
        count = 0
        for track in tracks:
            result = await self.add_track(chat_id, track, force=False if first else False)
            started = started or result.started
            count += 1
            first = False
        return count, started

    async def _play_track(self, chat_id: int, track: Track) -> None:
        state = self.state(chat_id)
        ffmpeg_parameters = None
        if track.start_at and track.start_at > 0:
            ffmpeg_parameters = f"--base ---start -ss {int(track.start_at)}"

        logger.info("Playing in %s: %s", chat_id, track.title)
        stream = MediaStream(
            track.source,
            audio_parameters=AudioQuality.HIGH,
            video_flags=MediaStream.Flags.IGNORE,
            ffmpeg_parameters=ffmpeg_parameters,
        )
        await asyncio.wait_for(
            self.calls.play(
                chat_id,
                stream,
                GroupCallConfig(auto_start=self.config.auto_start_voice_chat),
            ),
            timeout=60,
        )
        if state.volume != 100:
            try:
                await self.calls.change_volume_call(chat_id, state.volume)
            except Exception as exc:  # pragma: no cover - depends on Telegram state
                logger.debug("Volume apply failed: %s", exc)
        await self._send_now_playing(chat_id, track)

    async def _send_now_playing(self, chat_id: int, track: Track) -> None:
        text = (
            "<b>▶️ Now playing</b>\n\n"
            f"<b>{track.display_title}</b>\n"
            f"<b>Duration:</b> <code>{track.display_duration}</code>\n"
            f"<b>Requested by:</b> {html_user(track.requester_id, track.requester_name)}"
        )
        if track.start_at:
            text += f"\n<b>Seek:</b> <code>{format_duration(track.start_at)}</code>"
        if track.webpage_url:
            text += f'\n<a href="{track.webpage_url}">Source</a>'
        await self.bot.send_message(
            chat_id,
            text,
            reply_markup=self.controls_markup(),
            disable_web_page_preview=True,
        )

    def controls_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("⏸ Pause", callback_data="shion:pause"),
                    InlineKeyboardButton("▶️ Resume", callback_data="shion:resume"),
                ],
                [
                    InlineKeyboardButton("⏭ Skip", callback_data="shion:skip"),
                    InlineKeyboardButton("⏹ Stop", callback_data="shion:stop"),
                ],
                [InlineKeyboardButton("📜 Queue", callback_data="shion:queue")],
            ]
        )

    async def on_stream_end(self, chat_id: int) -> None:
        state = self.state(chat_id)
        next_track: Track | None = None
        leave = False
        ended_track: Track | None = None

        async with state.lock:
            if time.monotonic() < state.suppress_end_until:
                logger.debug("Suppressed stream-end in %s", chat_id)
                return
            if state.current is None:
                return

            ended_track = state.current
            if state.loop == LoopMode.ONE:
                next_track = ended_track.clone_for_replay()
                state.current = next_track
            else:
                if state.loop == LoopMode.QUEUE:
                    state.queue.append(ended_track.clone_for_replay())
                    ended_track = None  # do not cleanup the original local file yet
                if state.queue:
                    next_track = state.queue.popleft()
                    state.current = next_track
                    state.paused = False
                else:
                    state.current = None
                    state.paused = False
                    leave = self.config.auto_leave_when_queue_empty

        if ended_track:
            await self._cleanup_track(ended_track)
        if next_track:
            try:
                await self._play_track(chat_id, next_track)
            except Exception as exc:
                logger.exception("Autoplay next failed in %s", chat_id)
                await self.bot.send_message(chat_id, f"⚠️ Next track failed: <code>{exc}</code>")
                await self.on_stream_end(chat_id)
        elif leave:
            try:
                await self.calls.leave_call(chat_id)
            except Exception:
                pass
            await self.bot.send_message(chat_id, "✅ Queue finished. Voice chat left.")

    async def pause(self, chat_id: int) -> None:
        state = self.state(chat_id)
        if not state.current:
            raise RuntimeError("Nothing is playing")
        await self.calls.pause(chat_id)
        state.paused = True

    async def resume(self, chat_id: int) -> None:
        state = self.state(chat_id)
        if not state.current:
            raise RuntimeError("Nothing is playing")
        await self.calls.resume(chat_id)
        state.paused = False

    async def skip(self, chat_id: int, count: int = 1) -> Track | None:
        state = self.state(chat_id)
        next_track: Track | None = None
        cleanup: list[Track] = []
        async with state.lock:
            if state.current is None:
                raise RuntimeError("Nothing is playing")
            cleanup.append(state.current)
            for _ in range(max(0, count - 1)):
                if state.queue:
                    cleanup.append(state.queue.popleft())
            if state.queue:
                next_track = state.queue.popleft()
                state.current = next_track
                state.paused = False
                state.suppress_end_until = time.monotonic() + 4
            else:
                state.current = None
                state.paused = False
                state.suppress_end_until = time.monotonic() + 4

        for track in cleanup:
            await self._cleanup_track(track)

        if next_track:
            await self._play_track(chat_id, next_track)
            return next_track

        try:
            await self.calls.leave_call(chat_id)
        except Exception:
            pass
        return None

    async def stop(self, chat_id: int) -> None:
        state = self.state(chat_id)
        async with state.lock:
            state.suppress_end_until = time.monotonic() + 4
            await self._cleanup_queue(state)
            await self._cleanup_current(state)
            state.queue.clear()
            state.current = None
            state.paused = False
        try:
            await self.calls.leave_call(chat_id)
        except Exception:
            pass

    async def join(self, chat_id: int) -> None:
        await self.calls.play(
            chat_id,
            None,
            GroupCallConfig(auto_start=self.config.auto_start_voice_chat),
        )

    async def leave(self, chat_id: int) -> None:
        await self.stop(chat_id)

    async def seek(self, chat_id: int, seconds: int) -> Track:
        state = self.state(chat_id)
        async with state.lock:
            if state.current is None:
                raise RuntimeError("Nothing is playing")
            if state.current.is_live:
                raise RuntimeError("Live streams cannot be seeked")
            if state.current.duration and seconds >= state.current.duration:
                raise RuntimeError("Seek time is beyond track duration")
            state.current.start_at = max(0, int(seconds))
            state.paused = False
            state.suppress_end_until = time.monotonic() + 4
            track = state.current
        await self._play_track(chat_id, track)
        return track

    async def volume(self, chat_id: int, volume: int) -> int:
        volume = max(1, min(200, int(volume)))
        state = self.state(chat_id)
        if state.current is None:
            raise RuntimeError("Nothing is playing")
        state.volume = volume
        try:
            await self.calls.change_volume_call(chat_id, volume)
        except Exception as exc:  # pragma: no cover - depends on Telegram call state
            logger.exception("Volume change failed in %s", chat_id)
            raise RuntimeError(
                "Volume change failed because no active stream is connected. Use /play first."
            ) from exc
        return volume

    async def shuffle(self, chat_id: int) -> int:
        state = self.state(chat_id)
        async with state.lock:
            items = list(state.queue)
            random.shuffle(items)
            state.queue = deque(items)
            return len(state.queue)

    async def set_loop(self, chat_id: int, mode: str) -> str:
        mode = mode.lower().strip()
        if mode not in LoopMode.ALL:
            raise ValueError("Loop mode must be off, one, or queue")
        state = self.state(chat_id)
        state.loop = mode
        return mode

    def now_text(self, chat_id: int) -> str | None:
        state = self.state(chat_id)
        if not state.current:
            return None
        current = state.current
        paused = "Paused" if state.paused else "Playing"
        return (
            f"<b>🎧 {paused}</b>\n\n"
            f"{current.line()}\n"
            f"<b>Loop:</b> <code>{state.loop}</code> | <b>Volume:</b> <code>{state.volume}</code>"
        )

    def queue_text(self, chat_id: int, *, limit: int = 10) -> str:
        state = self.state(chat_id)
        if not state.current and not state.queue:
            return "The queue is empty."
        lines = ["<b>📜 Queue</b>"]
        if state.current:
            lines.append("\n<b>Now:</b>")
            lines.append(state.current.line())
        if state.queue:
            lines.append("\n<b>Next:</b>")
            for index, track in enumerate(list(state.queue)[:limit], start=1):
                lines.append(track.line(index))
            remaining = len(state.queue) - limit
            if remaining > 0:
                lines.append(f"…and {remaining} more")
        lines.append(
            f"\n<b>Loop:</b> <code>{state.loop}</code> | <b>Volume:</b> <code>{state.volume}</code>"
        )
        return "\n".join(lines)

    async def send_queue(self, chat_id: int) -> None:
        for chunk in split_text(self.queue_text(chat_id)):
            await self.bot.send_message(chat_id, chunk, disable_web_page_preview=True)

    async def _cleanup_current(self, state: QueueState) -> None:
        if state.current:
            await self._cleanup_track(state.current)

    async def _cleanup_queue(self, state: QueueState) -> None:
        for track in list(state.queue):
            await self._cleanup_track(track)

    @staticmethod
    async def _cleanup_track(track: Track) -> None:
        path = track.cleanup_path
        if not path:
            return
        try:
            path = Path(path)
            if path.exists() and path.is_file():
                await asyncio.to_thread(path.unlink)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.debug("Failed to cleanup %s: %s", path, exc)
