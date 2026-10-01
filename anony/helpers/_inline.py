"""Inline keyboard builders (pure data — no network, no state)."""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config


def stream_controls(chat_id: int) -> InlineKeyboardMarkup:
    """Playback control panel attached to 'now playing' messages."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏸ Pause", callback_data=f"ctr|pause|{chat_id}"),
                InlineKeyboardButton("⏭ Skip", callback_data=f"ctr|skip|{chat_id}"),
                InlineKeyboardButton("⏹ Stop", callback_data=f"ctr|stop|{chat_id}"),
            ],
            [
                InlineKeyboardButton("🔁 Loop", callback_data=f"ctr|loop|{chat_id}"),
                InlineKeyboardButton("📋 Queue", callback_data=f"ctr|queue|{chat_id}"),
                InlineKeyboardButton("✖ Close", callback_data=f"ctr|close|{chat_id}"),
            ],
        ]
    )


def start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add me to your group", url=config.deep_link("startgroup")
                ),
                InlineKeyboardButton("📡 Channel", url=config.SUPPORT_CHANNEL),
            ],
            [
                InlineKeyboardButton("💬 Support", url=config.SUPPORT_CHAT),
                InlineKeyboardButton("❓ Help", callback_data="nav|help"),
            ],
        ]
    )


def help_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="nav|settings"),
                InlineKeyboardButton("📊 Stats", callback_data="nav|stats"),
            ],
            [
                InlineKeyboardButton("➕ Add to group", url=config.deep_link("startgroup")),
                InlineKeyboardButton("✖ Close", callback_data="nav|close"),
            ],
        ]
    )


def settings_buttons(lang_code: str, cmd_delete: bool) -> InlineKeyboardMarkup:
    en_active = "🟢" if lang_code == "en" else "⚪"
    hi_active = "🟢" if lang_code == "hi" else "⚪"
    delete_state = "ON ✅" if cmd_delete else "OFF ❌"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"{en_active} English", callback_data="set|lang|en"),
                InlineKeyboardButton(f"{hi_active} हिन्दी", callback_data="set|lang|hi"),
            ],
            [
                InlineKeyboardButton(
                    f"🗑 Auto-delete commands: {delete_state}",
                    callback_data="set|cdelete",
                ),
            ],
            [InlineKeyboardButton("✖ Close", callback_data="nav|close")],
        ]
    )


def queue_buttons(page: int, pages: int) -> InlineKeyboardMarkup:
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("◀️", callback_data=f"queue|{page - 1}"))
    row.append(InlineKeyboardButton(f"📄 {page}/{pages}", callback_data="queue|noop"))
    if page < pages:
        row.append(InlineKeyboardButton("▶️", callback_data=f"queue|{page + 1}"))
    row.append(InlineKeyboardButton("✖ Close", callback_data="nav|close"))
    return InlineKeyboardMarkup([row])


def confirm_buttons(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"confirm|{action}"),
                InlineKeyboardButton("❌ No", callback_data="nav|close"),
            ]
        ]
    )
