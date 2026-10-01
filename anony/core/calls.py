"""PyTgCalls v3 voice-chat manager.

Wraps :class:`pytgcalls.PyTgCalls` (NTgCalls v3 native binding) behind a
small, chat-oriented API used by the player and plugins:

* :meth:`play`    — pipe a media URL (audio or video mode, optional seek)
* :meth:`pause` / :meth:`resume`
* :meth:`stop`    — leave the group call
* :meth:`time`    — current playback position in seconds
* :meth:`active_chats`
* :meth:`on_stream_end` — callback hook for the queue engine
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, List, Optional

from pytgcalls import PyTgCalls
from pytgcalls import filters as call_filters
from pytgcalls.types import GroupCallConfig, MediaStream, StreamEnded
from pytgcalls.types.stream import AudioQuality, VideoQuality

log = logging.getLogger(__name__)

StreamEndCallback = Callable[[int], Awaitable[None]]


class TgCall:
    """Thin, defensive wrapper around the PyTgCalls engine."""

    def __init__(self, userbot) -> None:
        self.userbot = userbot
        self.app = PyTgCalls(userbot)
        self._started = False
        self._on_stream_end: Optional[StreamEndCallback] = None

        # Register the stream-end dispatcher (PyTgCalls v3 update system).
        self.app.on_update(call_filters.stream_end())(self._dispatch_stream_end)

    # ── lifecycle ──────────────────────────────────────────────────
    async def start(self) -> None:
        if self._started:
            return
        # PyTgCalls starts (and waits for) the MTProto client itself when
        # it is not yet connected — see pytgcalls/methods/utilities/start.
        await self.app.start()
        self._started = True
        log.info("PyTgCalls client(s) started.")

    async def stop_all(self) -> None:
        """Leave every active group call (graceful shutdown)."""
        try:
            for chat_id in await self.active_chats():
                try:
                    await self.app.leave_call(chat_id)
                except Exception:  # noqa: BLE001 - best effort shutdown
                    pass
        except Exception as exc:  # noqa: BLE001
            log.warning("stop_all failed: %s", exc)

    # ── stream-end hook ────────────────────────────────────────────
    def on_stream_end(self, callback: StreamEndCallback) -> None:
        self._on_stream_end = callback

    async def _dispatch_stream_end(self, _client, update: StreamEnded) -> None:
        log.info("Stream ended in chat %s (type=%s).", update.chat_id, update.stream_type)
        if self._on_stream_end is None:
            return
        try:
            await self._on_stream_end(update.chat_id)
        except Exception:  # noqa: BLE001 - player errors must not kill updates
            log.exception("Stream-end handler failed for chat %s", update.chat_id)

    # ── playback control ───────────────────────────────────────────
    async def play(
        self,
        chat_id: int,
        url: str,
        video: bool = False,
        seek: int = 0,
        headers: Optional[dict] = None,
    ) -> None:
        """Pipe ``url`` into the voice chat of ``chat_id``.

        ``seek`` restarts the stream at an offset (ffmpeg ``-ss``).
        When a call is already active in the chat, PyTgCalls swaps the
        source seamlessly (``set_stream_sources``).
        """
        stream = MediaStream(
            url,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.SD_360p,
            audio_flags=MediaStream.Flags.AUTO_DETECT,
            video_flags=(
                MediaStream.Flags.AUTO_DETECT if video else MediaStream.Flags.IGNORE
            ),
            headers=headers or None,
            ffmpeg_parameters=f"-ss {int(seek)}" if seek > 0 else None,
        )
        await self.app.play(chat_id, stream, config=GroupCallConfig(auto_start=True))

    async def pause(self, chat_id: int) -> None:
        await self.app.pause(chat_id)

    async def resume(self, chat_id: int) -> None:
        await self.app.resume(chat_id)

    async def stop(self, chat_id: int) -> None:
        """Leave the group call in ``chat_id`` (ignores 'not in call')."""
        try:
            await self.app.leave_call(chat_id)
        except Exception as exc:  # noqa: BLE001 - NotInCallError etc.
            log.debug("leave_call(%s): %s", chat_id, exc)

    async def time(self, chat_id: int) -> int:
        """Current playback position in seconds (0 when not playing)."""
        try:
            return int(await self.app.time(chat_id))
        except Exception:  # noqa: BLE001 - NotInCallError etc.
            return 0

    async def active_chats(self) -> List[int]:
        try:
            # PyTgCalls v3 exposes ``calls`` as an async property, not a
            # callable. Calling it leaks the property coroutine and always
            # reports an empty active-call list.
            return list((await self.app.calls).keys())
        except Exception:  # noqa: BLE001
            return []

    def ping(self) -> float:
        """NTgCalls binding latency in milliseconds."""
        try:
            value = self.app.ping
            return value() if callable(value) else float(value)
        except Exception:  # noqa: BLE001
            return -1.0
