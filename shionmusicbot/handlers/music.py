from __future__ import annotations

import asyncio
import logging

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButtonStyle

from ..clients import CONFIG, assistant, bot, db, downloader, player
from ..decorators import admin_or_auth, group_only, is_authorized_user
from ..models import Track
from ..strings import (
    HELP_TEXT,
    NEED_ADMIN,
    NEED_QUERY,
    NO_QUEUE,
    NOTHING_PLAYING,
    VC_JOIN_HINT,
)
from ..utils import format_duration, html_user, is_url, parse_duration, split_text

logger = logging.getLogger(__name__)

BUTTON_PRIMARY = KeyboardButtonStyle(bg_primary=True)
BUTTON_SUCCESS = KeyboardButtonStyle(bg_success=True)
BOT_USERNAME: str | None = None


async def _bot_username() -> str | None:
    global BOT_USERNAME
    if BOT_USERNAME:
        return BOT_USERNAME
    me = getattr(bot, "me", None)
    username = getattr(me, "username", None)
    if not username:
        try:
            me = await bot.get_me()
            username = getattr(me, "username", None)
        except Exception:
            username = None
    BOT_USERNAME = username
    return BOT_USERNAME


async def _group_only_markup() -> InlineKeyboardMarkup | None:
    username = await _bot_username()
    if not username:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ",
                    url=(
                        f"https://t.me/{username}?startgroup=music"
                        "&admin=invite_users+delete_messages+manage_video_chats"
                    ),
                    style=BUTTON_SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    "📖 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs",
                    callback_data="shion:help",
                    style=BUTTON_PRIMARY,
                )
            ],
        ]
    )


def _cmd(names: str | list[str]):
    return filters.command(names, prefixes=list(CONFIG.command_prefixes))


def _args(message) -> str:
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _requester(message) -> tuple[int, str]:
    user = message.from_user
    if not user:
        return 0, "Anonymous"
    name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return user.id, name or (user.username or str(user.id))


async def _play_allowed(client, message) -> bool:
    dj_mode = await db.get_bool_setting(message.chat.id, "dj_mode", CONFIG.default_dj_mode)
    if not dj_mode:
        return True
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    return await is_authorized_user(client, message.chat.id, user_id)


async def _prepare_track(message, query: str, *, video: bool = False) -> Track:
    requester_id, requester_name = _requester(message)
    reply = message.reply_to_message
    if reply and not query:
        track = await downloader.from_telegram_reply(reply, requester_id, requester_name)
    elif query:
        track = await downloader.resolve(query, requester_id, requester_name, video=video)
    else:
        raise ValueError(NEED_QUERY)
    track.video = video
    return track


def _log_task_result(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc:
        logger.error("Background play task crashed", exc_info=(type(exc), exc, exc.__traceback__))


async def _safe_status(status, text: str) -> None:
    try:
        await status.edit_text(text, disable_web_page_preview=True)
    except Exception:
        pass


async def _reply_or_send(message, text: str, **kwargs):
    try:
        return await message.reply_text(text, **kwargs)
    except Exception:
        return await bot.send_message(message.chat.id, text, **kwargs)


def _friendly_play_error(exc: Exception) -> str:
    raw = str(exc)
    if (
        "CHANNEL_INVALID" in raw
        or "channels.GetChannels" in raw
        or "Assistant cannot access" in raw
    ):
        return (
            "⚠️ <b>Assistant cannot access this group</b>\n\n"
            "Telegram returned <code>CHANNEL_INVALID</code>, which means the assistant user "
            "account cannot resolve this group/channel from its own session.\n\n"
            "<b>Fix checklist:</b>\n"
            "1. Promote the bot with <b>Invite Users/Add Members</b> permission.\n"
            "2. Start/open the group voice chat.\n"
            "3. Use <code>/play song name</code>; I will auto-invite the assistant.\n"
            "4. If needed, promote the assistant with <b>Manage Voice Chats / Video Chats</b>.\n\n"
            "For old/basic private groups, convert to a supergroup if Telegram still "
            "rejects the assistant peer."
        )
    return f"⚠️ <b>Error:</b> <code>{raw}</code>\n\n{VC_JOIN_HINT}"


async def _run_play_request(message, status, query: str, *, force: bool, video: bool) -> None:
    try:
        await _safe_status(
            status,
            "🤖 <b>Checking assistant access</b>\n"
            "├ Auto-inviting assistant if this group needs it...\n"
            "└ Then I will prepare the stream.",
        )
        await player.ensure_assistant_joined(message.chat)
        if query:
            await _safe_status(
                status,
                "⚡ <b>Fast mode</b>\n"
                "├ Searching on Premium Tube/Testweb3...\n"
                "└ Preparing direct FFmpeg stream headers...",
            )
        else:
            await _safe_status(
                status,
                "📥 <b>Reply media mode</b>\n"
                "├ Downloading Telegram media first...\n"
                "└ Then I will stream the local file to VC.",
            )
        track = await _prepare_track(message, query, video=video)
        await _safe_status(
            status,
            "✅ <b>Source ready</b>\n"
            f"├ <b>{track.display_title}</b>\n"
            f"├ Mode: <code>{'video + screen-share' if track.video else 'audio'}</code>\n"
            f"└ Duration: <code>{track.display_duration}</code>\n\n"
            "📡 Connecting to Telegram voice chat...",
        )
        result = await player.add_track(message.chat.id, track, force=force)
    except Exception as exc:
        logger.exception("Play request failed in %s", getattr(message.chat, "id", "unknown"))
        text = _friendly_play_error(exc)
        try:
            await status.edit_text(text, disable_web_page_preview=True)
        except Exception:
            await _reply_or_send(message, text, disable_web_page_preview=True)
        return

    if result.started:
        try:
            await status.delete()
        except Exception:
            pass
    else:
        await status.edit_text(
            "<b>➕ Added to queue</b>\n"
            f"{track.line()}\n"
            f"<b>Mode:</b> <code>{'video' if track.video else 'audio'}</code>\n"
            f"<b>Position:</b> <code>{result.position}</code>",
            disable_web_page_preview=True,
        )


PRIVATE_GROUP_ONLY_TEXT = (
    "<b>🎧 Shion Music bot works in groups only</b>\n\n"
    "<code>/play</code>, <code>/vplay</code>, <code>/radio</code>, playlist and "
    "VC control commands need a Telegram group voice chat.\n\n"
    "<b>How to use:</b>\n"
    "1. Add me to your group.\n"
    "2. Give optional minimum admin permissions: <b>Invite Users/Add Members</b>, "
    "<b>Delete Messages</b>, and <b>Manage Voice Chats / Video Chats</b>.\n"
    "3. Start/open the group voice chat.\n"
    "4. Send <code>/play song name</code> or <code>/vplay song name</code> in the group.\n\n"
    "The assistant joins automatically when playback starts."
)


@bot.on_message(
    _cmd(
        [
            "play",
            "p",
            "playforce",
            "fplay",
            "vplay",
            "vstream",
            "radio",
            "stream",
            "playlist",
            "pl",
            "pause",
            "resume",
            "mute",
            "unmute",
            "skip",
            "stop",
            "join",
            "leave",
            "queue",
            "now",
            "mode",
            "seek",
            "volume",
            "loop",
            "shuffle",
        ]
    )
    & filters.private
)
async def private_music_command_handler(_, message):
    await _reply_or_send(
        message,
        PRIVATE_GROUP_ONLY_TEXT,
        reply_markup=await _group_only_markup(),
        disable_web_page_preview=True,
    )


@bot.on_message(_cmd(["play", "p", "playforce", "fplay", "vplay", "vstream"]) & filters.group)
@group_only
async def play_handler(client, message):
    player.remember_chat(message.chat)
    if not await _play_allowed(client, message):
        return await _reply_or_send(message, NEED_ADMIN)

    query = _args(message)
    if not query and not message.reply_to_message:
        return await _reply_or_send(message, NEED_QUERY)

    command = (message.command[0] or "").lower()
    force = command in {"playforce", "fplay"}
    stream_mode = await db.get_setting(message.chat.id, "stream_mode", "audio")
    video = command in {"vplay", "vstream"} or stream_mode == "video"
    status = await _reply_or_send(
        message, "📺 Fast video mode starting..." if video else "⚡ Fast audio mode starting..."
    )
    task = asyncio.create_task(_run_play_request(message, status, query, force=force, video=video))
    task.add_done_callback(_log_task_result)
    return None


@bot.on_message(_cmd(["radio", "stream"]) & filters.group)
@group_only
async def radio_handler(client, message):
    player.remember_chat(message.chat)
    if not await _play_allowed(client, message):
        return await _reply_or_send(message, NEED_ADMIN)
    query = _args(message)
    if not query or not is_url(query):
        return await _reply_or_send(
            message,
            "Send a direct radio/stream URL. Example: <code>/radio https://example.com/live.mp3</code>",
        )
    requester_id, requester_name = _requester(message)
    track = Track(
        title=query.rsplit("/", 1)[-1] or "Live radio",
        source=query,
        requester_id=requester_id,
        requester_name=requester_name,
        webpage_url=query,
        is_live=True,
    )
    status = await _reply_or_send(message, "📻 Starting radio stream...")
    try:
        await _safe_status(status, "🤖 Auto-inviting assistant if needed...")
        await player.ensure_assistant_joined(message.chat)
        result = await player.add_track(message.chat.id, track)
    except Exception as exc:
        return await status.edit_text(f"⚠️ <b>Error:</b> <code>{exc}</code>")
    if result.started:
        await status.delete()
    else:
        await status.edit_text(
            f"📻 Radio added to queue at position <code>{result.position}</code>."
        )


@bot.on_message(_cmd(["playlist", "pl"]) & filters.group)
@group_only
async def playlist_handler(client, message):
    player.remember_chat(message.chat)
    if not await _play_allowed(client, message):
        return await _reply_or_send(message, NEED_ADMIN)

    query = _args(message)
    if not query and message.reply_to_message:
        query = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not query:
        return await _reply_or_send(
            message, "Send a playlist URL or a newline-separated song list."
        )

    requester_id, requester_name = _requester(message)
    status = await _reply_or_send(message, "📜 Resolving playlist...")
    try:
        await _safe_status(status, "🤖 Auto-inviting assistant if needed...")
        await player.ensure_assistant_joined(message.chat)
        tracks: list[Track]
        lines = [line.strip() for line in query.splitlines() if line.strip()]
        if len(lines) > 1 and not is_url(query.strip()):
            lines = lines[: CONFIG.playlist_limit]
            tracks = list(
                await asyncio.gather(
                    *(downloader.resolve(line, requester_id, requester_name) for line in lines)
                )
            )
        else:
            tracks = await downloader.resolve_playlist(query, requester_id, requester_name)
        if not tracks:
            return await status.edit_text("No playable tracks found.")
        count, started = await player.add_many(message.chat.id, tracks[: CONFIG.playlist_limit])
    except Exception as exc:
        return await status.edit_text(f"⚠️ <b>Playlist error:</b> <code>{exc}</code>")

    text = f"✅ Added <code>{count}</code> track(s) to queue."
    if started:
        text += " First track started."
    await status.edit_text(text)


@bot.on_message(_cmd(["pause", "ps"]) & filters.group)
@admin_or_auth
async def pause_handler(_, message):
    try:
        await player.pause(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text("⏸ Paused.")


@bot.on_message(_cmd(["resume", "rs"]) & filters.group)
@admin_or_auth
async def resume_handler(_, message):
    try:
        await player.resume(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text("▶️ Resumed.")


@bot.on_message(_cmd(["mute", "m"]) & filters.group)
@admin_or_auth
async def mute_handler(_, message):
    try:
        await player.mute(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text("🔇 Stream muted.")


@bot.on_message(_cmd(["unmute", "um"]) & filters.group)
@admin_or_auth
async def unmute_handler(_, message):
    try:
        await player.unmute(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text("🔊 Stream unmuted.")


@bot.on_message(_cmd(["skip", "next"]) & filters.group)
@admin_or_auth
async def skip_handler(_, message):
    raw = _args(message)
    count = int(raw) if raw.isdigit() else 1
    try:
        next_track = await player.skip(message.chat.id, count=count)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    if next_track:
        await message.reply_text(f"⏭ Skipped. Now playing: <b>{next_track.display_title}</b>")
    else:
        await message.reply_text(
            "⏭ Skipped. Queue finished. I will leave VC after 5 minutes of inactivity."
        )


@bot.on_message(_cmd(["stop", "end", "cancel"]) & filters.group)
@admin_or_auth
async def stop_handler(_, message):
    await player.stop(message.chat.id)
    await message.reply_text("⏹ Stopped and left voice chat.")


@bot.on_message(_cmd(["join", "joinvc"]) & filters.group)
@admin_or_auth
async def join_handler(_, message):
    player.remember_chat(message.chat)
    try:
        await player.ensure_assistant_joined(message.chat)
        await player.join(message.chat.id)
    except Exception as exc:
        return await message.reply_text(_friendly_play_error(exc), disable_web_page_preview=True)
    await message.reply_text("✅ Joined voice chat.")


@bot.on_message(_cmd(["assistant", "inviteassistant"]) & filters.group)
@admin_or_auth
async def assistant_handler(client, message):
    player.remember_chat(message.chat)
    raw = _args(message)
    try:
        me = await assistant.get_me()
        invite = raw.strip() if raw and ("t.me/" in raw or raw.startswith("+")) else None
        if invite:
            try:
                await assistant.join_chat(invite)
            except Exception as exc:
                if "already" not in str(exc).lower() and "participant" not in str(exc).lower():
                    raise
        else:
            invite = await client.export_chat_invite_link(message.chat.id)
            try:
                await assistant.join_chat(invite)
            except Exception as exc:
                if "already" not in str(exc).lower() and "participant" not in str(exc).lower():
                    raise
        await message.reply_text(
            "✅ Assistant is connected to this group.\n"
            f"<b>Assistant:</b> {html_user(me.id, me.first_name)}\n\n"
            "Now start/open the voice chat and use <code>/join</code> or <code>/play song</code>."
        )
    except Exception as exc:
        await message.reply_text(
            "⚠️ Assistant invite failed.\n\n"
            "Make the bot admin with invite-link permission, or send an invite link like:\n"
            "<code>/assistant https://t.me/+invite_code</code>\n\n"
            f"<b>Details:</b> <code>{exc}</code>"
        )


@bot.on_message(_cmd(["leave", "leavevc"]) & filters.group)
@admin_or_auth
async def leave_handler(_, message):
    await player.leave(message.chat.id)
    await message.reply_text("👋 Left voice chat.")


@bot.on_message(_cmd(["active", "streams"]))
async def active_handler(_, message):
    await message.reply_text(player.active_text(), disable_web_page_preview=True)


@bot.on_message(_cmd(["queue", "q", "list"]) & filters.group)
@group_only
async def queue_handler(_, message):
    text = player.queue_text(message.chat.id)
    if text == "The queue is empty.":
        return await message.reply_text(NO_QUEUE)
    for chunk in split_text(text):
        await message.reply_text(chunk, disable_web_page_preview=True)


@bot.on_message(_cmd(["now", "np", "current"]) & filters.group)
@group_only
async def now_handler(_, message):
    text = player.now_text(message.chat.id)
    if not text:
        return await message.reply_text(NOTHING_PLAYING)
    await message.reply_text(
        text, reply_markup=player.controls_markup(), disable_web_page_preview=True
    )


@bot.on_message(_cmd("seek") & filters.group)
@admin_or_auth
async def seek_handler(_, message):
    raw = _args(message)
    if not raw:
        return await message.reply_text("Example: <code>/seek 1:20</code>")
    try:
        seconds = parse_duration(raw)
        track = await player.seek(message.chat.id, seconds)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text(
        f"⏩ Seeked to <code>{format_duration(seconds)}</code> in <b>{track.display_title}</b>."
    )


@bot.on_message(_cmd(["volume", "vol"]) & filters.group)
@admin_or_auth
async def volume_handler(_, message):
    raw = _args(message)
    if not raw or not raw.isdigit():
        return await message.reply_text("Example: <code>/volume 100</code> (1-200)")
    try:
        volume = await player.volume(message.chat.id, int(raw))
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text(f"🔊 Volume set to <code>{volume}</code>.")


@bot.on_message(_cmd(["mode", "switch"]) & filters.group)
@admin_or_auth
async def mode_handler(_, message):
    raw = _args(message).lower().strip()
    if raw not in {"audio", "video"}:
        current = await db.get_setting(message.chat.id, "stream_mode", "audio")
        return await message.reply_text(
            "<b>Current stream mode:</b> "
            f"<code>{current}</code>\n\n"
            "Use <code>/mode audio</code> for normal voice-chat audio or "
            "<code>/mode video</code> for screen-share video by default. "
            "You can always use <code>/vplay</code> for one video stream."
        )
    await db.set_setting(message.chat.id, "stream_mode", raw)
    await message.reply_text(f"✅ Default stream mode set to <code>{raw}</code>.")


@bot.on_message(_cmd("loop") & filters.group)
@admin_or_auth
async def loop_handler(_, message):
    raw = _args(message).lower()
    if not raw:
        return await message.reply_text(
            "Loop modes: <code>off</code>, <code>one</code>, <code>queue</code>"
        )
    try:
        mode = await player.set_loop(message.chat.id, raw)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text(f"🔁 Loop mode: <code>{mode}</code>")


@bot.on_message(_cmd("shuffle") & filters.group)
@admin_or_auth
async def shuffle_handler(_, message):
    count = await player.shuffle(message.chat.id)
    await message.reply_text(f"🔀 Shuffled <code>{count}</code> queued track(s).")


async def _target_user(client, message) -> tuple[int, str] | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        name = " ".join(part for part in [user.first_name, user.last_name] if part) or str(user.id)
        return user.id, name
    raw = _args(message)
    if not raw:
        return None
    try:
        user = await client.get_users(raw)
    except Exception:
        if raw.lstrip("-").isdigit():
            return int(raw), raw
        raise
    name = " ".join(part for part in [user.first_name, user.last_name] if part) or str(user.id)
    return user.id, name


@bot.on_message(_cmd("auth") & filters.group)
@admin_or_auth
async def auth_handler(client, message):
    target = await _target_user(client, message)
    if not target:
        return await message.reply_text(
            "Reply to a user or provide a user ID/username. Example: <code>/auth @user</code>"
        )
    user_id, name = target
    await db.add_auth_user(message.chat.id, user_id)
    await message.reply_text(f"✅ Authorized DJ: {html_user(user_id, name)}")


@bot.on_message(_cmd("unauth") & filters.group)
@admin_or_auth
async def unauth_handler(client, message):
    target = await _target_user(client, message)
    if not target:
        return await message.reply_text("Reply to a user or provide a user ID/username.")
    user_id, name = target
    await db.remove_auth_user(message.chat.id, user_id)
    await message.reply_text(f"✅ Removed DJ permission: {html_user(user_id, name)}")


@bot.on_message(_cmd("authusers") & filters.group)
@admin_or_auth
async def authusers_handler(_, message):
    users = await db.list_auth_users(message.chat.id)
    if not users:
        return await message.reply_text("No authorized DJs in this chat.")
    lines = ["<b>Authorized DJs</b>"] + [f"• <code>{user_id}</code>" for user_id in users]
    await message.reply_text("\n".join(lines))


@bot.on_message(_cmd("dj") & filters.group)
@admin_or_auth
async def dj_handler(_, message):
    raw = _args(message).lower()
    if raw not in {"on", "off"}:
        current = await db.get_bool_setting(message.chat.id, "dj_mode", CONFIG.default_dj_mode)
        mode = "on" if current else "off"
        return await message.reply_text(
            f"DJ mode is <code>{mode}</code>. Use <code>/dj on</code> or <code>/dj off</code>."
        )
    await db.set_setting(message.chat.id, "dj_mode", "true" if raw == "on" else "false")
    await message.reply_text(f"🎚 DJ mode turned <code>{raw}</code>.")


@bot.on_message(_cmd("settings") & filters.group)
@group_only
async def settings_handler(_, message):
    dj_mode = await db.get_bool_setting(message.chat.id, "dj_mode", CONFIG.default_dj_mode)
    stream_mode = await db.get_setting(message.chat.id, "stream_mode", "audio")
    state = player.state(message.chat.id)
    await message.reply_text(
        "<b>⚙️ Chat settings</b>\n"
        f"DJ mode: <code>{'on' if dj_mode else 'off'}</code>\n"
        f"Stream mode: <code>{stream_mode}</code>\n"
        f"Loop: <code>{state.loop}</code>\n"
        f"Volume: <code>{state.volume}</code>\n"
        f"Muted: <code>{'yes' if state.muted else 'no'}</code>\n"
        f"Queue size: <code>{len(state.queue)}</code>"
    )


@bot.on_callback_query(filters.regex(r"^shion:"))
async def callback_handler(client, query):
    action = query.data.split(":", 1)[1]
    if action == "help":
        await query.message.edit_text(HELP_TEXT, disable_web_page_preview=True)
        return await query.answer()

    message = query.message
    if not message or not message.chat:
        return await query.answer("Message expired.", show_alert=True)
    chat_id = message.chat.id
    user_id = getattr(query.from_user, "id", None)

    if action in {
        "pause",
        "resume",
        "mute",
        "unmute",
        "skip",
        "stop",
    } and not await is_authorized_user(client, chat_id, user_id):
        return await query.answer("Admin/DJ only.", show_alert=True)

    try:
        if action == "pause":
            await player.pause(chat_id)
            text = player.now_text(chat_id) or NOTHING_PLAYING
            await query.message.edit_text(
                text, reply_markup=player.controls_markup(), disable_web_page_preview=True
            )
            await query.answer("Paused")
        elif action == "resume":
            await player.resume(chat_id)
            text = player.now_text(chat_id) or NOTHING_PLAYING
            await query.message.edit_text(
                text, reply_markup=player.controls_markup(), disable_web_page_preview=True
            )
            await query.answer("Resumed")
        elif action == "mute":
            await player.mute(chat_id)
            text = player.now_text(chat_id) or NOTHING_PLAYING
            await query.message.edit_text(
                text, reply_markup=player.controls_markup(), disable_web_page_preview=True
            )
            await query.answer("Muted")
        elif action == "unmute":
            await player.unmute(chat_id)
            text = player.now_text(chat_id) or NOTHING_PLAYING
            await query.message.edit_text(
                text, reply_markup=player.controls_markup(), disable_web_page_preview=True
            )
            await query.answer("Unmuted")
        elif action == "skip":
            try:
                await query.message.delete()
            except Exception:
                pass
            await player.skip(chat_id)
            await query.answer("Skipped")
        elif action == "stop":
            await player.stop(chat_id)
            await query.message.edit_text("⏹ Stopped and left voice chat.")
            await query.answer("Stopped")
        elif action == "queue":
            await query.message.edit_text(player.queue_text(chat_id), disable_web_page_preview=True)
            await query.answer("Queue updated")
        else:
            await query.answer("Unknown action", show_alert=True)
    except Exception as exc:
        await query.answer(str(exc), show_alert=True)
