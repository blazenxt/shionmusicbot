from __future__ import annotations

import re
from html import escape
from urllib.parse import urlparse

_TIME_PART_RE = re.compile(r"^(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})$")


def is_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def truncate(text: str | None, limit: int = 60) -> str:
    if not text:
        return "Unknown"
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def html_user(user_id: int, name: str | None = None) -> str:
    label = escape(name or str(user_id))
    return f'<a href="tg://user?id={user_id}">{label}</a>'


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "Live"
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def parse_duration(value: str) -> int:
    """Parse 90, 1:30, 01:02:03, 2m10s, 1h5m into seconds."""
    value = value.strip().lower()
    if not value:
        raise ValueError("empty duration")
    if value.isdigit():
        return int(value)

    match = _TIME_PART_RE.match(value)
    if match:
        hours = int(match.group("h") or 0)
        minutes = int(match.group("m"))
        seconds = int(match.group("s"))
        return hours * 3600 + minutes * 60 + seconds

    token_re = re.compile(
        r"(?P<num>\d+)\s*(?P<unit>h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)"
    )
    total = 0
    matched = False
    for token in token_re.finditer(value):
        matched = True
        number = int(token.group("num"))
        unit = token.group("unit")
        if unit.startswith("h"):
            total += number * 3600
        elif unit.startswith("m"):
            total += number * 60
        else:
            total += number
    if matched:
        return total
    raise ValueError(f"invalid duration: {value}")


def human_size(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "unknown"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def split_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            chunks.append("".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks
