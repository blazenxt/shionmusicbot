"""Multilingual translation handler.

Language packs are plain JSON files inside ``anony/locales`` (``en.json``,
``hi.json`` …).  Handlers use the ``@lang.language()`` decorator which
attaches a per-chat :class:`Translator` to the update as ``update.lang``;
string access then is simply ``message.lang.playing_now``.  For ad-hoc
use there is ``await lang.t(chat_id, "key", **context)``.
"""

from __future__ import annotations

import functools
import json
import logging
from pathlib import Path
from typing import Callable, Dict, Optional

from config import config

log = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


class _SafeDict(dict):
    """Leaves unknown {placeholders} untouched instead of raising."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "{" + key + "}"


class Translator:
    """Attribute-access proxy over one language pack."""

    __slots__ = ("_service", "_code")

    def __init__(self, service: "Lang", code: str) -> None:
        object.__setattr__(self, "_service", service)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> str:
        return object.__getattribute__(self, "_code")

    def get(self, key: str) -> str:
        service = object.__getattribute__(self, "_service")
        code = object.__getattribute__(self, "_code")
        return service.get(code, key)

    def format(self, key: str, **context) -> str:
        return self.get(key).format_map(_SafeDict(context))

    def __getattr__(self, key: str) -> str:
        return self.get(key)


class Lang:
    """Translation service bound to the state engine (for per-chat language)."""

    def __init__(self, db=None) -> None:
        self.db = db
        self.strings: Dict[str, Dict[str, str]] = {}
        self.load()

    # ── loading ────────────────────────────────────────────────────
    def load(self) -> None:
        self.strings = {}
        if not LOCALES_DIR.is_dir():
            log.warning("Locales directory missing: %s", LOCALES_DIR)
            self.strings["en"] = {}
            return
        for path in sorted(LOCALES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.strings[path.stem.lower()] = {
                        str(k): str(v) for k, v in data.items()
                    }
            except (OSError, ValueError) as exc:
                log.warning("Skipping locale %s: %s", path.name, exc)
        self.strings.setdefault("en", {})
        log.info(
            "Loaded %d language pack(s): %s",
            len(self.strings),
            ", ".join(sorted(self.strings)),
        )

    # ── access ─────────────────────────────────────────────────────
    def codes(self) -> list:
        return sorted(self.strings)

    def get(self, code: Optional[str], key: str) -> str:
        pack = self.strings.get((code or "en").lower())
        if pack and key in pack:
            return pack[key]
        return self.strings.get("en", {}).get(key, key)

    async def t(self, chat_id: Optional[int], key: str, **context) -> str:
        """Translate ``key`` for ``chat_id`` with optional ``{placeholders}``."""
        code = config.LANG_CODE
        if self.db is not None and chat_id is not None:
            try:
                code = await self.db.get_lang(chat_id)
            except Exception:  # noqa: BLE001 - translation must never crash
                pass
        text = self.get(code, key)
        return text.format_map(_SafeDict(context)) if context else text

    # ── decorator ──────────────────────────────────────────────────
    def language(self, func=None):
        """Wrap a Pyrogram handler and inject ``update.lang``.

        Usable both as ``@lang.language`` and ``@lang.language()``.
        """

        if func is None:  # called as a factory: @lang.language()
            return self.language

        @functools.wraps(func)
        async def wrapper(client, update, *args, **kwargs):
            chat_id = None
            chat = getattr(update, "chat", None)
            if chat is not None and getattr(chat, "id", None) is not None:
                chat_id = chat.id
            else:
                inner = getattr(update, "message", None)
                inner_chat = getattr(inner, "chat", None)
                if inner_chat is not None and getattr(inner_chat, "id", None) is not None:
                    chat_id = inner_chat.id

            code = config.LANG_CODE
            if self.db is not None and chat_id is not None:
                try:
                    code = await self.db.get_lang(chat_id)
                except Exception:  # noqa: BLE001
                    pass
            update.lang = Translator(self, code)
            return await func(client, update, *args, **kwargs)

        return wrapper
