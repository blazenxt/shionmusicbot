"""Inline keyboard builders (pure data — no network, no state)."""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButtonStyle

from config import config

# Telegram API 9.4 semantic button styles. Clients that support 9.4 render
# these as blue (primary), green (success) and red (danger).
PRIMARY = KeyboardButtonStyle(bg_primary=True)
SUCCESS = KeyboardButtonStyle(bg_success=True)
DANGER = KeyboardButtonStyle(bg_danger=True)


def stream_controls(chat_id: int) -> InlineKeyboardMarkup:
    """Playback control panel attached to 'now playing' messages."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏸ Pause", callback_data=f"ctr|pause|{chat_id}", style=PRIMARY),
                InlineKeyboardButton("⏭ Skip", callback_data=f"ctr|skip|{chat_id}", style=PRIMARY),
                InlineKeyboardButton("⏹ Stop", callback_data=f"ctr|stop|{chat_id}", style=DANGER),
            ],
            [
                InlineKeyboardButton("🔁 Loop", callback_data=f"ctr|loop|{chat_id}", style=SUCCESS),
                InlineKeyboardButton("📋 Queue", callback_data=f"ctr|queue|{chat_id}", style=PRIMARY),
                InlineKeyboardButton("✖ Close", callback_data=f"ctr|close|{chat_id}", style=DANGER),
            ],
        ]
    )


def start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add me to your group", url=config.deep_link("startgroup"), style=SUCCESS
                ),
                InlineKeyboardButton("📡 Channel", url=config.SUPPORT_CHANNEL, style=PRIMARY),
            ],
            [
                InlineKeyboardButton("💬 Support", url=config.SUPPORT_CHAT, style=PRIMARY),
                InlineKeyboardButton("❓ Help", callback_data="nav|help", style=PRIMARY),
            ],
        ]
    )


def help_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="nav|settings", style=PRIMARY),
                InlineKeyboardButton("📊 Stats", callback_data="nav|stats", style=PRIMARY),
            ],
            [
                InlineKeyboardButton("➕ Add to group", url=config.deep_link("startgroup"), style=SUCCESS),
                InlineKeyboardButton("✖ Close", callback_data="nav|close", style=DANGER),
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
                InlineKeyboardButton(f"{en_active} English", callback_data="set|lang|en", style=SUCCESS if lang_code == "en" else PRIMARY),
                InlineKeyboardButton(f"{hi_active} हिन्दी", callback_data="set|lang|hi", style=SUCCESS if lang_code == "hi" else PRIMARY),
            ],
            [
                InlineKeyboardButton(
                    f"🗑 Auto-delete commands: {delete_state}",
                    callback_data="set|cdelete",
                    style=SUCCESS if cmd_delete else DANGER,
                ),
            ],
            [InlineKeyboardButton("✖ Close", callback_data="nav|close", style=DANGER)],
        ]
    )


def queue_buttons(page: int, pages: int) -> InlineKeyboardMarkup:
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("◀️", callback_data=f"queue|{page - 1}", style=PRIMARY))
    row.append(InlineKeyboardButton(f"📄 {page}/{pages}", callback_data="queue|noop", style=PRIMARY))
    if page < pages:
        row.append(InlineKeyboardButton("▶️", callback_data=f"queue|{page + 1}", style=PRIMARY))
    row.append(InlineKeyboardButton("✖ Close", callback_data="nav|close", style=DANGER))
    return InlineKeyboardMarkup([row])


def confirm_buttons(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"confirm|{action}", style=SUCCESS),
                InlineKeyboardButton("❌ No", callback_data="nav|close", style=DANGER),
            ]
        ]
    )
