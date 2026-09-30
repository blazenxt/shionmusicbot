from __future__ import annotations

import asyncio
import logging

from pyrogram import filters

from ..clients import CONFIG, bot, db, downloader, player
from ..decorators import admin_or_auth, group_only, is_authorized_user
from ..models import Track
from ..strings import (
    HELP_TEXT,
    NEED_ADMIN,
    NEED_QUERY,
    NO_QUEUE,
    NOTHING_PLAYING,
    SEARCHING,
    VC_JOIN_HINT,
)
from ..utils import format_duration, html_user, is_url, parse_duration, split_text

logger = logging.getLogger(__name__)


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
        track = await downloader.resolve(query, requester_id, requester_name)
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


async def _run_play_request(message, status, query: str, *, force: bool, video: bool) -> None:
    try:
        track = await _prepare_track(message, query, video=video)
        result = await player.add_track(message.chat.id, track, force=force)
    except Exception as exc:
        logger.exception("Play request failed in %s", getattr(message.chat, "id", "unknown"))
        text = f"⚠️ <b>Error:</b> <code>{exc}</code>\n\n{VC_JOIN_HINT}"
        try:
            await status.edit_text(text)
        except Exception:
            await message.reply_text(text)
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


@bot.on_message(_cmd(["play", "p", "playforce", "fplay", "vplay", "vstream"]) & filters.group)
@group_only
async def play_handler(client, message):
    if not await _play_allowed(client, message):
        return await message.reply_text(NEED_ADMIN)

    query = _args(message)
    if not query and not message.reply_to_message:
        return await message.reply_text(NEED_QUERY)

    command = (message.command[0] or "").lower()
    force = command in {"playforce", "fplay"}
    video = command in {"vplay", "vstream"}
    status = await message.reply_text("📺 Preparing video stream..." if video else SEARCHING)
    task = asyncio.create_task(_run_play_request(message, status, query, force=force, video=video))
    task.add_done_callback(_log_task_result)
    return None


@bot.on_message(_cmd(["radio", "stream"]) & filters.group)
@group_only
async def radio_handler(client, message):
    if not await _play_allowed(client, message):
        return await message.reply_text(NEED_ADMIN)
    query = _args(message)
    if not query or not is_url(query):
        return await message.reply_text(
            "Send a direct radio/stream URL. Example: <code>/radio https://example.com/live.mp3</code>"
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
    status = await message.reply_text("📻 Starting radio stream...")
    try:
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
    if not await _play_allowed(client, message):
        return await message.reply_text(NEED_ADMIN)

    query = _args(message)
    if not query and message.reply_to_message:
        query = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not query:
        return await message.reply_text("Send a playlist URL or a newline-separated song list.")

    requester_id, requester_name = _requester(message)
    status = await message.reply_text("📜 Resolving playlist...")
    try:
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


@bot.on_message(_cmd(["pause"]) & filters.group)
@admin_or_auth
async def pause_handler(_, message):
    try:
        await player.pause(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text("⏸ Paused.")


@bot.on_message(_cmd(["resume"]) & filters.group)
@admin_or_auth
async def resume_handler(_, message):
    try:
        await player.resume(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>")
    await message.reply_text("▶️ Resumed.")


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
        await message.reply_text("⏭ Skipped. Queue finished.")


@bot.on_message(_cmd(["stop", "end", "cancel"]) & filters.group)
@admin_or_auth
async def stop_handler(_, message):
    await player.stop(message.chat.id)
    await message.reply_text("⏹ Stopped and left voice chat.")


@bot.on_message(_cmd(["join", "joinvc"]) & filters.group)
@admin_or_auth
async def join_handler(_, message):
    try:
        await player.join(message.chat.id)
    except Exception as exc:
        return await message.reply_text(f"⚠️ <code>{exc}</code>\n\n{VC_JOIN_HINT}")
    await message.reply_text("✅ Joined voice chat.")


@bot.on_message(_cmd(["leave", "leavevc"]) & filters.group)
@admin_or_auth
async def leave_handler(_, message):
    await player.leave(message.chat.id)
    await message.reply_text("👋 Left voice chat.")


@bot.on_message(_cmd(["queue", "q"]) & filters.group)
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
    state = player.state(message.chat.id)
    await message.reply_text(
        "<b>⚙️ Chat settings</b>\n"
        f"DJ mode: <code>{'on' if dj_mode else 'off'}</code>\n"
        f"Loop: <code>{state.loop}</code>\n"
        f"Volume: <code>{state.volume}</code>\n"
        f"Queue size: <code>{len(state.queue)}</code>"
    )


@bot.on_callback_query(filters.regex(r"^shion:"))
async def callback_handler(client, query):
    action = query.data.split(":", 1)[1]
    if action == "help":
        await query.message.reply_text(HELP_TEXT, disable_web_page_preview=True)
        return await query.answer()

    message = query.message
    if not message or not message.chat:
        return await query.answer("Message expired.", show_alert=True)
    chat_id = message.chat.id
    user_id = getattr(query.from_user, "id", None)

    if action in {"pause", "resume", "skip", "stop"} and not await is_authorized_user(
        client, chat_id, user_id
    ):
        return await query.answer("Admin/DJ only.", show_alert=True)

    try:
        if action == "pause":
            await player.pause(chat_id)
            await query.answer("Paused")
        elif action == "resume":
            await player.resume(chat_id)
            await query.answer("Resumed")
        elif action == "skip":
            await player.skip(chat_id)
            await query.answer("Skipped")
        elif action == "stop":
            await player.stop(chat_id)
            await query.answer("Stopped")
        elif action == "queue":
            await query.answer("Queue sent")
            await player.send_queue(chat_id)
        else:
            await query.answer("Unknown action", show_alert=True)
    except Exception as exc:
        await query.answer(str(exc), show_alert=True)
