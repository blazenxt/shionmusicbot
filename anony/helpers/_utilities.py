"""Small formatting / parsing utilities shared by all plugins."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

_URL_RE = re.compile(r"https?://[^\s]+")


def fmt_duration(seconds) -> str:
    """Render seconds as ``h:mm:ss`` / ``m:ss``."""
    try:
        seconds = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        seconds = 0
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_duration(text: str) -> int:
    """Parse ``h:mm:ss`` / ``mm:ss`` / ``ss`` into seconds (0 on error)."""
    if not text:
        return 0
    parts = str(text).strip().split(":")
    if not parts or not all(p.strip().isdigit() for p in parts if p != ""):
        return 0
    try:
        values = [int(p or 0) for p in parts]
    except ValueError:
        return 0
    if len(values) > 3:
        return 0
    seconds = 0
    for value in values:
        seconds = seconds * 60 + value
    return seconds


def get_urls(text: Optional[str]) -> List[str]:
    """Extract every http(s) URL from a text blob."""
    if not text:
        return []
    return _URL_RE.findall(text)


def extract_query(message) -> Optional[str]:
    """Best-effort query extraction from a command message.

    Order of preference:
    1. text after the command (``/play faded alan walker``),
    2. the replied-to message's text/caption.
    """
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    tokens = text.split(maxsplit=1)
    args = tokens[1].strip() if len(tokens) > 1 else ""

    if not args:
        reply = getattr(message, "reply_to_message", None)
        if reply is not None:
            args = (
                getattr(reply, "text", None) or getattr(reply, "caption", None) or ""
            ).strip()

    return args or None


def human_count(value) -> str:
    """1234567 → ``1.2M``."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= divisor:
            return f"{value / divisor:.1f}{suffix}"
    return str(value)


def truncate(text: str, limit: int = 64) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def play_log(chat_id: int, user, track) -> None:
    """Append a play event to ``data/plays.log`` (best effort, never raises)."""
    try:
        from anony.core.dir import DATA

        DATA.mkdir(parents=True, exist_ok=True)
        user_id = getattr(user, "id", "?")
        user_name = getattr(user, "first_name", None) or getattr(user, "title", "?")
        line = (
            f"{__import__('time').strftime('%Y-%m-%d %H:%M:%S')} | "
            f"chat={chat_id} user={user_id}({user_name}) | "
            f"{track.media.video_id} | {track.media.title}\n"
        )
        with open(Path(DATA) / "plays.log", "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
