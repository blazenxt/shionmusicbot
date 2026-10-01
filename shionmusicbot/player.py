from __future__ import annotations

import asyncio
import logging
import random
import shlex
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque

from ntgcalls import MediaSource
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButtonStyle
from pytgcalls import filters as call_filters
from pytgcalls.types import GroupCallConfig, StreamEnded
from pytgcalls.types.raw import AudioParameters, AudioStream, Stream, VideoParameters, VideoStream

from .models import Track
from .utils import format_duration, html_user, split_text

logger = logging.getLogger(__name__)

IDLE_VOICE_LEAVE_SECONDS = 5 * 60
IDLE_GROUP_LEAVE_SECONDS = 60 * 60
BUTTON_PRIMARY = KeyboardButtonStyle(bg_primary=True)
BUTTON_SUCCESS = KeyboardButtonStyle(bg_success=True)
BUTTON_DANGER = KeyboardButtonStyle(bg_danger=True)


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
    muted: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    suppress_end_until: float = 0.0
    idle_voice_task: asyncio.Task | None = None
    idle_group_task: asyncio.Task | None = None


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
        self._chat_refs: dict[int, int | str] = {}
        self._handlers_registered = False

    def state(self, chat_id: int) -> QueueState:
        if chat_id not in self._states:
            self._states[chat_id] = QueueState()
        return self._states[chat_id]

    def remember_chat(self, chat) -> None:
        """Remember the best assistant-side reference for a Telegram chat.

        PyTgCalls uses the assistant user account, not the bot account, to resolve
        the voice-chat peer. Public supergroups resolve more reliably by username;
        private groups still use the numeric id and require the assistant to be a
        member of the group.
        """
        chat_id = getattr(chat, "id", None)
        if chat_id is None:
            return
        username = getattr(chat, "username", None)
        self._chat_refs[int(chat_id)] = f"@{username}" if username else int(chat_id)

    def _chat_target(self, chat_id: int) -> int | str:
        return self._chat_refs.get(chat_id, chat_id)

    async def ensure_assistant_joined(self, chat) -> None:
        """Make the assistant user join the target group when playback is requested.

        The bot account handles commands, while the assistant account joins the
        group/voice-chat only when needed. Public groups are joined by username;
        private groups are joined through an invite link exported by the bot.
        """
        self.remember_chat(chat)
        chat_id = int(getattr(chat, "id"))
        app = getattr(self.calls, "mtproto_client", None)
        if app is None:
            return

        try:
            me = await app.get_me()
            member = await app.get_chat_member(chat_id, me.id)
            status = str(getattr(member, "status", "")).lower()
            if "left" not in status and "banned" not in status and "kicked" not in status:
                await self._refresh_assistant_peer(app, chat_id)
                return
        except Exception as exc:
            logger.debug("Assistant membership check failed for %s: %s", chat_id, exc)

        username = getattr(chat, "username", None)
        join_errors: list[str] = []
        if username:
            target = f"@{username}"
            self._chat_refs[chat_id] = target
            # Public groups can be resolved and played by username. Do not require
            # numeric -100 peer resolution here; PyrogramMod can fail to parse a
            # successful public join as ChatInviteJoinResultOk on some Telegram layers.
            try:
                await app.get_chat(target)
            except Exception as exc:
                logger.debug("Assistant public get_chat failed for %s: %s", target, exc)
            try:
                await app.join_chat(target)
                await app.get_chat(target)
                return
            except Exception as exc:
                raw = str(exc).lower()
                if "already" in raw or "participant" in raw or "user_already" in raw:
                    return
                # Important: if Telegram joined the public group but PyrogramMod
                # raised while parsing the response, get_chat(@username) still works.
                # In that case continue with @username instead of trying an invite
                # link that requires bot admin rights.
                try:
                    await app.get_chat(target)
                    logger.info(
                        "Assistant public join for %s accepted after parse warning: %s",
                        target,
                        exc,
                    )
                    return
                except Exception:
                    pass
                join_errors.append(type(exc).__name__)
                logger.debug("Assistant public join failed for %s: %s", chat_id, exc)

        try:
            invite = await self.bot.export_chat_invite_link(chat_id)
        except Exception as exc:
            hint = (
                "Assistant is not in this private group and I could not create an invite link. "
                "Promote the bot as admin with Invite Users/Add Members permission, "
                "then use /play again."
            )
            if join_errors:
                hint += f" Public username join failed: {', '.join(join_errors)}."
            raise RuntimeError(hint) from exc

        try:
            await app.join_chat(invite)
        except Exception as exc:
            raw = str(exc).lower()
            if "already" not in raw and "participant" not in raw and "user_already" not in raw:
                raise RuntimeError(
                    "Assistant auto-invite failed. Revoke bad invite links if needed, "
                    "then promote the bot with Invite Users permission and retry /play."
                ) from exc
        await self._refresh_assistant_peer(app, chat_id)

    async def _refresh_assistant_peer(self, app, chat_id: int) -> None:
        try:
            await app.resolve_peer(chat_id)
            return
        except Exception:
            pass
        try:
            async for dialog in app.get_dialogs():
                dialog_chat = getattr(dialog, "chat", None)
                if getattr(dialog_chat, "id", None) == chat_id:
                    break
        except Exception as exc:
            logger.debug("Assistant dialog refresh failed for %s: %s", chat_id, exc)
        await app.resolve_peer(chat_id)

    async def _warm_assistant_peer(self, chat_id: int) -> int | str:
        target = self._chat_target(chat_id)
        app = getattr(self.calls, "mtproto_client", None)
        if app is None:
            return target

        if isinstance(target, str):
            try:
                await app.get_chat(target)
                return target
            except Exception as exc:
                logger.debug("Assistant could not pre-resolve %s: %s", target, exc)

        try:
            await self._refresh_assistant_peer(app, chat_id)
        except Exception as exc:
            raise RuntimeError(
                "Assistant cannot access this group/channel. Public groups are joined by "
                "@username automatically. For private groups, promote the bot with Invite "
                "Users/Add Members permission so it can auto-invite the assistant, then "
                "try /play again."
            ) from exc
        return target

    @staticmethod
    def _cancel_idle_leave(state: QueueState) -> None:
        if state.idle_voice_task and not state.idle_voice_task.done():
            state.idle_voice_task.cancel()
        if state.idle_group_task and not state.idle_group_task.done():
            state.idle_group_task.cancel()
        state.idle_voice_task = None
        state.idle_group_task = None

    def _schedule_idle_leave(self, chat_id: int) -> None:
        state = self.state(chat_id)
        self._cancel_idle_leave(state)
        state.idle_voice_task = asyncio.create_task(self._idle_voice_leave_after(chat_id))
        state.idle_group_task = asyncio.create_task(self._idle_group_leave_after(chat_id))

    async def _idle_voice_leave_after(self, chat_id: int) -> None:
        try:
            await asyncio.sleep(IDLE_VOICE_LEAVE_SECONDS)
            state = self.state(chat_id)
            async with state.lock:
                if state.current or state.queue:
                    return
                state.idle_voice_task = None
            try:
                await self.calls.leave_call(self._chat_target(chat_id))
            except Exception:
                pass
            await self.bot.send_message(
                chat_id,
                "👋 No new /play or /vplay for 5 minutes. Assistant left the voice chat.",
            )
        except asyncio.CancelledError:
            return

    async def _idle_group_leave_after(self, chat_id: int) -> None:
        try:
            await asyncio.sleep(IDLE_GROUP_LEAVE_SECONDS)
            state = self.state(chat_id)
            async with state.lock:
                if state.current or state.queue:
                    return
                state.idle_group_task = None
            try:
                await self.calls.leave_call(self._chat_target(chat_id))
            except Exception:
                pass
            app = getattr(self.calls, "mtproto_client", None)
            if app is not None:
                try:
                    await app.leave_chat(chat_id, delete=True)
                except TypeError:
                    try:
                        await app.leave_chat(chat_id)
                    except Exception:
                        pass
                except Exception as exc:
                    logger.debug("Assistant group idle leave failed in %s: %s", chat_id, exc)
            await self.bot.send_message(
                chat_id,
                "👋 Assistant left this group after 1 hour of inactivity. "
                "Use /play again and I will auto-invite it when needed.",
            )
        except asyncio.CancelledError:
            return

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
                self._cancel_idle_leave(state)
                await self._cleanup_queue(state)
                await self._cleanup_current(state)
                state.queue.clear()
                state.current = track
                state.paused = False
                state.suppress_end_until = time.monotonic() + 4
                should_start = True
                position = 0
            elif state.current is None:
                self._cancel_idle_leave(state)
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
                    await self.calls.leave_call(self._chat_target(chat_id))
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

    def _ffmpeg_input_args(self, track: Track) -> list[str]:
        args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "quiet"]
        if track.start_at and track.start_at > 0:
            args += ["-ss", str(int(track.start_at))]
        if track.source.startswith(("http://", "https://")):
            args += [
                "-rw_timeout",
                "15000000",
                "-reconnect",
                "1",
                "-reconnect_at_eof",
                "1",
                "-reconnect_streamed",
                "1",
                "-reconnect_on_network_error",
                "1",
                "-reconnect_on_http_error",
                "4xx,5xx",
                "-reconnect_delay_max",
                "5",
                "-fflags",
                "+discardcorrupt",
                "-err_detect",
                "ignore_err",
            ]
        if track.headers:
            header_blob = "".join(f"{key}: {value}\r\n" for key, value in track.headers.items())
            args += ["-headers", header_blob]
        args += ["-i", track.source]
        return args

    def _audio_command(self, track: Track) -> str:
        args = self._ffmpeg_input_args(track)
        args += ["-vn", "-f", "s16le", "-ac", "2", "-ar", "48000", "pipe:1"]
        return shlex.join(args)

    def _video_command(self, track: Track) -> str:
        args = self._ffmpeg_input_args(track)
        args += [
            "-an",
            "-f",
            "rawvideo",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "pipe:1",
        ]
        return shlex.join(args)

    def _build_fast_stream(self, track: Track) -> Stream:
        audio_parameters = AudioParameters(48000, 2)
        microphone = AudioStream(
            MediaSource.SHELL,
            self._audio_command(track),
            audio_parameters,
        )
        screen = None
        if track.video:
            screen = VideoStream(
                MediaSource.SHELL,
                self._video_command(track),
                VideoParameters(1280, 720, 30, adjust_by_height=False),
            )
        return Stream(microphone=microphone, screen=screen)

    async def _play_track(self, chat_id: int, track: Track) -> None:
        state = self.state(chat_id)

        logger.info(
            "Playing in %s: %s%s",
            chat_id,
            track.title,
            " [video]" if track.video else "",
        )
        stream = self._build_fast_stream(track)
        target = await self._warm_assistant_peer(chat_id)
        try:
            await asyncio.wait_for(
                self.calls.play(
                    target,
                    stream,
                    GroupCallConfig(auto_start=self.config.auto_start_voice_chat),
                ),
                timeout=60,
            )
        except Exception as exc:
            raw = str(exc)
            if "CHANNEL_INVALID" in raw or "channels.GetChannels" in raw:
                raise RuntimeError(
                    "Telegram rejected this group as CHANNEL_INVALID for the assistant account. "
                    "Public groups are resolved by @username automatically. For private groups, "
                    "let the bot auto-invite the assistant or add the assistant once manually."
                ) from exc
            if "CHAT_ADMIN_REQUIRED" in raw and (
                "CreateGroupCall" in raw or "phone.CreateGroupCall" in raw
            ):
                raise RuntimeError(
                    "Voice chat is not active, and Telegram did not allow the assistant to "
                    "start it. Start/open the group voice chat manually, or promote the "
                    "assistant with Manage Voice Chats / Video Chats permission, then use "
                    "/play or /vplay again."
                ) from exc
            raise
        if state.volume != 100:
            try:
                await self.calls.change_volume_call(self._chat_target(chat_id), state.volume)
            except Exception as exc:  # pragma: no cover - depends on Telegram state
                logger.debug("Volume apply failed: %s", exc)
        if state.muted:
            try:
                await self.calls.mute(self._chat_target(chat_id))
            except Exception as exc:  # pragma: no cover - depends on Telegram state
                logger.debug("Mute apply failed: %s", exc)
        await self._send_now_playing(chat_id, track)

    async def _send_now_playing(self, chat_id: int, track: Track) -> None:
        mode = "📺 Video / screen share" if track.video else "🎧 Audio"
        text = (
            "<b>╭─── ᴺᴼᵂ ᴾᴸᴬʸᴵᴺᴳ ───╮</b>\n"
            f"<b>│ {track.display_title}</b>\n"
            f"<b>│ Mode:</b> <code>{mode}</code>\n"
            f"<b>│ Duration:</b> <code>{track.display_duration}</code>\n"
            f"<b>╰ Requested by:</b> {html_user(track.requester_id, track.requester_name)}"
        )
        if track.start_at:
            text += f"\n<b>Seek:</b> <code>{format_duration(track.start_at)}</code>"
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
                    InlineKeyboardButton(
                        "⏸ ᴘᴀᴜsᴇ", callback_data="shion:pause", style=BUTTON_PRIMARY
                    ),
                    InlineKeyboardButton(
                        "▶ ʀᴇsᴜᴍᴇ", callback_data="shion:resume", style=BUTTON_SUCCESS
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔇 ᴍᴜᴛᴇ", callback_data="shion:mute", style=BUTTON_DANGER
                    ),
                    InlineKeyboardButton(
                        "🔊 ᴜɴᴍᴜᴛᴇ", callback_data="shion:unmute", style=BUTTON_SUCCESS
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⏭ sᴋɪᴘ", callback_data="shion:skip", style=BUTTON_PRIMARY
                    ),
                    InlineKeyboardButton("⏹ sᴛᴏᴘ", callback_data="shion:stop", style=BUTTON_DANGER),
                ],
                [
                    InlineKeyboardButton(
                        "📜 ǫᴜᴇᴜᴇ", callback_data="shion:queue", style=BUTTON_PRIMARY
                    )
                ],
            ]
        )

    async def on_stream_end(self, chat_id: int) -> None:
        state = self.state(chat_id)
        next_track: Track | None = None
        schedule_idle_leave = False
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
                    state.muted = False
                    schedule_idle_leave = self.config.auto_leave_when_queue_empty

        if ended_track:
            await self._cleanup_track(ended_track)
        if next_track:
            try:
                await self._play_track(chat_id, next_track)
            except Exception as exc:
                logger.exception("Autoplay next failed in %s", chat_id)
                await self.bot.send_message(chat_id, f"⚠️ Next track failed: <code>{exc}</code>")
                await self.on_stream_end(chat_id)
        elif schedule_idle_leave:
            self._schedule_idle_leave(chat_id)
            await self.bot.send_message(
                chat_id,
                "✅ Queue finished. I will leave the voice chat after 5 minutes "
                "of inactivity. Assistant will leave this group after 1 hour "
                "if nobody uses /play or /vplay.",
            )

    async def pause(self, chat_id: int) -> None:
        state = self.state(chat_id)
        if not state.current:
            raise RuntimeError("Nothing is playing")
        await self.calls.pause(self._chat_target(chat_id))
        state.paused = True

    async def resume(self, chat_id: int) -> None:
        state = self.state(chat_id)
        if not state.current:
            raise RuntimeError("Nothing is playing")
        await self.calls.resume(self._chat_target(chat_id))
        state.paused = False

    async def mute(self, chat_id: int) -> None:
        state = self.state(chat_id)
        if not state.current:
            raise RuntimeError("Nothing is playing")
        await self.calls.mute(self._chat_target(chat_id))
        state.muted = True

    async def unmute(self, chat_id: int) -> None:
        state = self.state(chat_id)
        if not state.current:
            raise RuntimeError("Nothing is playing")
        await self.calls.unmute(self._chat_target(chat_id))
        state.muted = False

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

        if self.config.auto_leave_when_queue_empty:
            self._schedule_idle_leave(chat_id)
        return None

    async def stop(self, chat_id: int) -> None:
        state = self.state(chat_id)
        async with state.lock:
            self._cancel_idle_leave(state)
            state.suppress_end_until = time.monotonic() + 4
            await self._cleanup_queue(state)
            await self._cleanup_current(state)
            state.queue.clear()
            state.current = None
            state.paused = False
            state.muted = False
        try:
            await self.calls.leave_call(self._chat_target(chat_id))
        except Exception:
            pass

    async def join(self, chat_id: int) -> None:
        target = await self._warm_assistant_peer(chat_id)
        await self.calls.play(
            target,
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
            await self.calls.change_volume_call(self._chat_target(chat_id), volume)
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
        icon = "📺" if current.video else "🎧"
        muted = "muted" if state.muted else "unmuted"
        return (
            f"<b>{icon} {paused}</b>\n\n"
            f"{current.line()}\n"
            f"<b>Mode:</b> <code>{'video' if current.video else 'audio'}</code> | "
            f"<b>Loop:</b> <code>{state.loop}</code> | "
            f"<b>Volume:</b> <code>{state.volume}</code> | "
            f"<b>Mute:</b> <code>{muted}</code>"
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
            f"\n<b>Loop:</b> <code>{state.loop}</code> | "
            f"<b>Volume:</b> <code>{state.volume}</code> | "
            f"<b>Mute:</b> <code>{'on' if state.muted else 'off'}</code>"
        )
        return "\n".join(lines)

    def active_text(self) -> str:
        active = [(chat_id, state) for chat_id, state in self._states.items() if state.current]
        if not active:
            return "No active voice chat streams."
        lines = ["<b>📡 Active Shion streams</b>"]
        for index, (chat_id, state) in enumerate(active, start=1):
            assert state.current is not None
            mode = "video" if state.current.video else "audio"
            lines.append(
                f"{index}. <code>{chat_id}</code> — <b>{state.current.display_title}</b> "
                f"(<code>{mode}</code>, queue <code>{len(state.queue)}</code>)"
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
