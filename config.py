"""
ShionMusicBot — environment configuration loader.

Reads configuration from environment variables and the optional ``.env``
file located next to this module.  Every value has a safe default so that
importing this module never raises; call :func:`validate` in the boot
sequence for explicit, human friendly errors on missing credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional at runtime, pinned in requirements.txt
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)

_TRUTHY = {"1", "true", "yes", "on", "y", "t"}
_FALSY = {"0", "false", "no", "off", "n", "f", ""}


def _str(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    raw = raw.strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration (exposed as :data:`config`)."""

    # ── Telegram core ────────────────────────────────────────────────
    API_ID: int = 0
    API_HASH: str = ""
    BOT_TOKEN: str = ""
    BOT_USERNAME: str = "ShionMusicBot"
    OWNER_ID: int = 0
    OWNER_USERNAME: str = ""

    # ── Assistant (userbot) account ──────────────────────────────────
    SESSION1: str = ""
    SESSION_STRING: str = ""
    ASSISTANT_ID: int = 0
    ASSISTANT_USERNAME: str = "ShionVCAssistant"

    # ── Community links ──────────────────────────────────────────────
    SUPPORT_CHANNEL: str = "https://t.me/"
    SUPPORT_CHAT: str = "https://t.me/"

    # ── Testweb3 YouTube proxy (single-source streaming policy) ──────
    YT_API_BASE: str = "http://Testweb3.cstsc.in/yt/"

    # ── Limits & behaviour ───────────────────────────────────────────
    DURATION_LIMIT: int = 60          # minutes
    QUEUE_LIMIT: int = 20
    PLAYLIST_LIMIT: int = 20
    AUTO_LEAVE: bool = False
    AUTO_END: bool = False
    THUMB_GEN: bool = False
    VIDEO_PLAY: bool = True
    LANG_CODE: str = "en"

    # ── Process ──────────────────────────────────────────────────────
    WORKERS: int = 8

    # ── Derived helpers ──────────────────────────────────────────────
    @property
    def duration_limit_secs(self) -> int:
        """Duration limit converted to seconds."""
        return max(1, self.DURATION_LIMIT) * 60

    @property
    def assistant_session(self) -> str:
        """Preferred session string (SESSION_STRING wins, SESSION1 fallback)."""
        return self.SESSION_STRING or self.SESSION1

    @property
    def owner_link(self) -> str:
        return f"https://t.me/{self.OWNER_USERNAME}" if self.OWNER_USERNAME else "https://t.me/"

    def deep_link(self, name: str = "startgroup") -> str:
        return f"https://t.me/{self.BOT_USERNAME}?{name}=true"


def _build() -> Config:
    session1 = _str("SESSION1")
    return Config(
        API_ID=_int("API_ID", 0),
        API_HASH=_str("API_HASH"),
        BOT_TOKEN=_str("BOT_TOKEN"),
        BOT_USERNAME=_str("BOT_USERNAME", "ShionMusicBot"),
        OWNER_ID=_int("OWNER_ID", 0),
        OWNER_USERNAME=_str("OWNER_USERNAME"),
        SESSION1=session1,
        SESSION_STRING=_str("SESSION_STRING") or session1,
        ASSISTANT_ID=_int("ASSISTANT_ID", 0),
        ASSISTANT_USERNAME=_str("ASSISTANT_USERNAME", "ShionVCAssistant"),
        SUPPORT_CHANNEL=_str("SUPPORT_CHANNEL", "https://t.me/"),
        SUPPORT_CHAT=_str("SUPPORT_CHAT", "https://t.me/"),
        YT_API_BASE=_str("YT_API_BASE", "http://Testweb3.cstsc.in/yt/").rstrip("/") + "/",
        DURATION_LIMIT=_int("DURATION_LIMIT", 60),
        QUEUE_LIMIT=_int("QUEUE_LIMIT", 20),
        PLAYLIST_LIMIT=_int("PLAYLIST_LIMIT", 20),
        AUTO_LEAVE=_bool("AUTO_LEAVE", False),
        AUTO_END=_bool("AUTO_END", False),
        THUMB_GEN=_bool("THUMB_GEN", False),
        VIDEO_PLAY=_bool("VIDEO_PLAY", True),
        LANG_CODE=_str("LANG_CODE", "en").lower() or "en",
        WORKERS=_int("WORKERS", max(4, min(16, (os.cpu_count() or 2) * 2))),
    )


config: Config = _build()


def validate() -> list:
    """Return a list of human readable configuration problems (empty == ok)."""
    problems = []
    if config.API_ID <= 0:
        problems.append("API_ID is missing or invalid")
    if len(config.API_HASH) < 32:
        problems.append("API_HASH is missing or invalid")
    if ":" not in config.BOT_TOKEN:
        problems.append("BOT_TOKEN is missing or invalid")
    if not config.assistant_session:
        problems.append("SESSION1 / SESSION_STRING is missing")
    if config.OWNER_ID <= 0:
        problems.append("OWNER_ID is missing or invalid")
    return problems
