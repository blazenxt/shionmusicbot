from __future__ import annotations

import time

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .. import __version__
from ..clients import CONFIG, bot, player
from ..strings import ABOUT_TEXT, HELP_TEXT, START_TEXT
from ..utils import format_duration

START_TIME = time.monotonic()


def _cmd(names: str | list[str]):
    return filters.command(names, prefixes=list(CONFIG.command_prefixes))


@bot.on_message(_cmd(["start", "alive"]))
async def start_handler(_, message):
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📖 Help", callback_data="shion:help")]])
    await message.reply_text(START_TEXT, reply_markup=markup, disable_web_page_preview=True)


@bot.on_message(_cmd(["help", "commands"]))
async def help_handler(_, message):
    await message.reply_text(HELP_TEXT, disable_web_page_preview=True)


@bot.on_message(_cmd(["about", "repo"]))
async def about_handler(_, message):
    await message.reply_text(ABOUT_TEXT + "\n\nRepo: https://github.com/blazenxt/shionmusicbot")


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
