from __future__ import annotations

import asyncio
import re
import time

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButtonStyle

from .. import __version__
from ..clients import CONFIG, bot, db, player
from ..strings import ABOUT_TEXT, HELP_TEXT, START_TEXT
from ..utils import format_duration

START_TIME = time.monotonic()
BUTTON_PRIMARY = KeyboardButtonStyle(bg_primary=True)
BUTTON_SUCCESS = KeyboardButtonStyle(bg_success=True)
BUTTON_DANGER = KeyboardButtonStyle(bg_danger=True)
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


async def _home_markup() -> InlineKeyboardMarkup:
    username = await _bot_username()
    rows = [
        [
            InlineKeyboardButton(
                "📖 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs", callback_data="shion:help", style=BUTTON_PRIMARY
            )
        ]
    ]
    if username:
        rows.insert(
            0,
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
        )
    return InlineKeyboardMarkup(rows)


async def _reply_or_send(message, text: str, **kwargs):
    try:
        return await message.reply_text(text, **kwargs)
    except Exception:
        return await bot.send_message(message.chat.id, text, **kwargs)


def _cmd(names: str | list[str]):
    return filters.command(names, prefixes=list(CONFIG.command_prefixes))


async def _delete_later(message, delay: int = 4) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


_prefix_pattern = "".join(re.escape(prefix) for prefix in CONFIG.command_prefixes)


@bot.on_message(filters.group, group=-2)
async def group_seen_warmup_handler(_, message):
    """Warm chat state even when /start was never used in the group."""
    try:
        player.remember_chat(message.chat)
        asyncio.create_task(db.touch_chat(message.chat.id, getattr(message.chat, "title", None)))
    except Exception:
        pass


@bot.on_message(filters.group & filters.regex(rf"^[{_prefix_pattern}][A-Za-z0-9_@]+"), group=-1)
async def auto_delete_command_handler(_, message):
    asyncio.create_task(_delete_later(message))


@bot.on_message(_cmd(["start", "alive"]))
async def start_handler(_, message):
    text = START_TEXT
    if getattr(message.chat, "type", None) == ChatType.PRIVATE:
        text += (
            "\n\n<b>DM note:</b> Music commands like <code>/play</code>, "
            "<code>/vplay</code>, <code>/pause</code>, and <code>/skip</code> work only "
            "inside Telegram groups with an active voice chat. Add me to a group "
            "using the button below."
        )
    else:
        text += "\n\nUse <code>/play song name</code> directly; /start is not required."
    await _reply_or_send(
        message, text, reply_markup=await _home_markup(), disable_web_page_preview=True
    )


@bot.on_message(_cmd(["help", "commands"]))
async def help_handler(_, message):
    await _reply_or_send(
        message, HELP_TEXT, reply_markup=await _home_markup(), disable_web_page_preview=True
    )


@bot.on_message(_cmd(["about", "repo"]))
async def about_handler(_, message):
    await _reply_or_send(
        message,
        ABOUT_TEXT + "\n\nRepo: https://github.com/blazenxt/shionmusicbot",
        reply_markup=await _home_markup(),
        disable_web_page_preview=True,
    )


@bot.on_message(_cmd("ping"))
async def ping_handler(_, message):
    start = time.monotonic()
    reply = await message.reply_text("🏓 Pinging...")
    latency = (time.monotonic() - start) * 1000
    uptime = format_duration(int(time.monotonic() - START_TIME))
    await reply.edit_text(
        f"🏓 <b>Pong!</b> <code>{latency:.0f} ms</code>\n⏱ Uptime: <code>{uptime}</code>"
    )


@bot.on_message(_cmd("stats"))
async def stats_handler(_, message):
    active = sum(1 for state in player._states.values() if state.current)  # noqa: SLF001
    queued = sum(len(state.queue) for state in player._states.values())  # noqa: SLF001
    uptime = format_duration(int(time.monotonic() - START_TIME))
    await message.reply_text(
        "<b>📊 Shion stats</b>\n"
        f"Version: <code>{__version__}</code>\n"
        f"Active chats: <code>{active}</code>\n"
        f"Queued tracks: <code>{queued}</code>\n"
        f"Uptime: <code>{uptime}</code>"
    )
