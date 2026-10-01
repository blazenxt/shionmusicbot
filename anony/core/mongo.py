"""High-speed in-memory state engine with a MongoDB-flavoured interface.

ShionMusicBot runs 100% reliably **without** any external database
cluster.  This module implements the classic music-bot storage interface
(``get_play_mode``, ``set_play_mode``, ``get_admins``, ``is_auth``,
``add_auth``, ``get_lang``, ``get_cmd_delete``, ``is_chat``, ``add_chat``,
``is_user``, ``add_user`` …) on plain in-memory structures guarded by a
re-entrant lock, and transparently snapshots state to
``data/state.json`` so restarts keep auth lists, sudoers, languages,
blacklists and counters.

Every public accessor is ``async`` so plugins can be migrated to a real
MongoDB later without touching a single call site.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from anony.core.dir import DATA
from config import config

log = logging.getLogger(__name__)


class DB:
    """Zero-dependency, thread-safe, in-memory bot database."""

    VERSION = 1

    def __init__(self, state_file: Optional[str] = None) -> None:
        self._state_file = state_file or str(DATA / "state.json")
        self._lock = threading.RLock()
        self._play_mode: Dict[int, str] = {}
        self._langs: Dict[int, str] = {}
        self._cmd_delete: Dict[int, bool] = {}
        self._auth_users: Dict[int, List[int]] = defaultdict(list)
        self._sudoers: Set[int] = set()
        self._blacklisted: Set[int] = set()
        self._chats: Set[int] = set()
        self._users: Set[int] = set()
        self._loop: Dict[int, int] = {}
        self._counters: Dict[str, int] = defaultdict(int)

    # ══ persistence ════════════════════════════════════════════════
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": self.VERSION,
                "play_mode": self._play_mode,
                "langs": self._langs,
                "cmd_delete": self._cmd_delete,
                "auth_users": {str(k): list(v) for k, v in self._auth_users.items()},
                "sudoers": sorted(self._sudoers),
                "blacklisted": sorted(self._blacklisted),
                "chats": sorted(self._chats),
                "users": sorted(self._users),
                "loop": self._loop,
                "counters": dict(self._counters),
            }

    def load(self) -> None:
        """Restore persisted state (called once during boot)."""
        try:
            if not os.path.exists(self._state_file):
                return
            with open(self._state_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("state root is not an object")
        except (OSError, ValueError) as exc:
            log.warning("State file unreadable (%s) — starting fresh.", exc)
            return

        with self._lock:
            self._play_mode = {int(k): v for k, v in (data.get("play_mode") or {}).items()}
            self._langs = {int(k): v for k, v in (data.get("langs") or {}).items()}
            self._cmd_delete = {int(k): bool(v) for k, v in (data.get("cmd_delete") or {}).items()}
            self._auth_users = defaultdict(
                list, {int(k): list(v) for k, v in (data.get("auth_users") or {}).items()}
            )
            self._sudoers = {int(x) for x in data.get("sudoers") or []}
            self._blacklisted = {int(x) for x in data.get("blacklisted") or []}
            self._chats = {int(x) for x in data.get("chats") or []}
            self._users = {int(x) for x in data.get("users") or []}
            self._loop = {int(k): int(v) for k, v in (data.get("loop") or {}).items()}
            self._counters = defaultdict(int, data.get("counters") or {})

        log.info(
            "State restored from %s (%d chats, %d users).",
            self._state_file,
            len(self._chats),
            len(self._users),
        )

    def save(self) -> None:
        """Atomically snapshot state to disk (called on shutdown & autosave)."""
        payload = self.to_dict()
        tmp = self._state_file + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp, self._state_file)
        except OSError as exc:
            log.warning("Could not persist state: %s", exc)

    # ══ play mode ══════════════════════════════════════════════════
    async def get_play_mode(self, chat_id: int) -> str:
        with self._lock:
            return self._play_mode.get(chat_id, "audio")

    async def set_play_mode(self, chat_id: int, mode: str) -> None:
        with self._lock:
            self._play_mode[chat_id] = "video" if mode == "video" else "audio"

    # ══ language ═══════════════════════════════════════════════════
    async def get_lang(self, chat_id: Optional[int]) -> str:
        if chat_id is None:
            return config.LANG_CODE
        with self._lock:
            return self._langs.get(chat_id, config.LANG_CODE)

    async def set_lang(self, chat_id: int, code: str) -> None:
        with self._lock:
            self._langs[chat_id] = str(code).lower()

    # ══ command auto-delete ════════════════════════════════════════
    async def get_cmd_delete(self, chat_id: int) -> bool:
        with self._lock:
            return self._cmd_delete.get(chat_id, False)

    async def set_cmd_delete(self, chat_id: int, enabled: bool) -> None:
        with self._lock:
            self._cmd_delete[chat_id] = bool(enabled)

    # ══ served chats / users ═══════════════════════════════════════
    async def is_chat(self, chat_id: int) -> bool:
        with self._lock:
            return chat_id in self._chats

    async def add_chat(self, chat_id: int) -> None:
        with self._lock:
            self._chats.add(int(chat_id))

    async def rm_chat(self, chat_id: int) -> None:
        with self._lock:
            self._chats.discard(int(chat_id))

    async def get_chats(self) -> List[int]:
        with self._lock:
            return sorted(self._chats)

    async def is_user(self, user_id: int) -> bool:
        with self._lock:
            return user_id in self._users

    async def add_user(self, user_id: int) -> None:
        with self._lock:
            self._users.add(int(user_id))

    async def get_users(self) -> List[int]:
        with self._lock:
            return sorted(self._users)

    # ══ sudoers (owner delegates) ══════════════════════════════════
    async def get_admins(self) -> List[int]:
        with self._lock:
            return sorted(self._sudoers)

    async def add_admin(self, user_id: int) -> None:
        with self._lock:
            self._sudoers.add(int(user_id))

    async def del_admin(self, user_id: int) -> None:
        with self._lock:
            self._sudoers.discard(int(user_id))

    async def is_sudo(self, user_id: Optional[int]) -> bool:
        if user_id is None:
            return False
        if user_id == config.OWNER_ID:
            return True
        with self._lock:
            return user_id in self._sudoers

    # ══ per-chat authorised users ══════════════════════════════════
    async def is_auth(self, chat_id: int, user_id: Optional[int]) -> bool:
        if user_id is None:
            return False
        with self._lock:
            return int(user_id) in self._auth_users.get(int(chat_id), [])

    async def add_auth(self, chat_id: int, user_id: int) -> bool:
        with self._lock:
            bucket = self._auth_users[int(chat_id)]
            if int(user_id) in bucket:
                return False
            bucket.append(int(user_id))
            return True

    async def unauth(self, chat_id: int, user_id: int) -> bool:
        with self._lock:
            bucket = self._auth_users.get(int(chat_id))
            if not bucket or int(user_id) not in bucket:
                return False
            bucket.remove(int(user_id))
            return True

    async def get_auth(self, chat_id: int) -> List[int]:
        with self._lock:
            return list(self._auth_users.get(int(chat_id), []))

    # ══ chat blacklist ═════════════════════════════════════════════
    async def is_blacklisted(self, chat_id: int) -> bool:
        with self._lock:
            return chat_id in self._blacklisted

    async def blacklist_chat(self, chat_id: int) -> None:
        with self._lock:
            self._blacklisted.add(int(chat_id))

    async def whitelist_chat(self, chat_id: int) -> None:
        with self._lock:
            self._blacklisted.discard(int(chat_id))

    async def get_blacklisted_chats(self) -> List[int]:
        with self._lock:
            return sorted(self._blacklisted)

    # ══ loop ═══════════════════════════════════════════════════════
    async def get_loop(self, chat_id: int) -> int:
        with self._lock:
            return self._loop.get(chat_id, 0)

    async def set_loop(self, chat_id: int, count: int) -> None:
        with self._lock:
            self._loop[int(chat_id)] = max(0, int(count))

    # ══ counters ═══════════════════════════════════════════════════
    async def incr_counter(self, name: str, by: int = 1) -> int:
        with self._lock:
            self._counters[name] += by
            return self._counters[name]

    async def get_counter(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    async def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "chats": len(self._chats),
                "users": len(self._users),
                "sudoers": len(self._sudoers),
                "blacklisted": len(self._blacklisted),
                "plays": self._counters.get("plays", 0),
            }
