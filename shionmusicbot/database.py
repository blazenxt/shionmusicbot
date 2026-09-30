from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Iterable


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_at INTEGER DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (chat_id, user_id)
            )
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            )
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS known_chats (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
            """
        )

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database.setup() was not called")
        return self._conn

    async def _execute(self, query: str, params: Iterable[object] = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self.conn.execute, query, tuple(params))
            await asyncio.to_thread(self.conn.commit)

    async def _fetchall(self, query: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
        async with self._lock:
            cursor = await asyncio.to_thread(self.conn.execute, query, tuple(params))
            rows = await asyncio.to_thread(cursor.fetchall)
            await asyncio.to_thread(cursor.close)
            return list(rows)

    async def _fetchone(self, query: str, params: Iterable[object] = ()) -> sqlite3.Row | None:
        rows = await self._fetchall(query, params)
        return rows[0] if rows else None

    async def touch_chat(self, chat_id: int, title: str | None) -> None:
        await self._execute(
            """
            INSERT INTO known_chats(chat_id, title, updated_at)
            VALUES(?, ?, strftime('%s', 'now'))
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                updated_at = excluded.updated_at
            """,
            (chat_id, title),
        )

    async def known_chats(self) -> list[int]:
        rows = await self._fetchall("SELECT chat_id FROM known_chats ORDER BY updated_at DESC")
        return [int(row["chat_id"]) for row in rows]

    async def add_auth_user(self, chat_id: int, user_id: int) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO auth_users(chat_id, user_id) VALUES(?, ?)",
            (chat_id, user_id),
        )

    async def remove_auth_user(self, chat_id: int, user_id: int) -> None:
        await self._execute(
            "DELETE FROM auth_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )

    async def is_auth_user(self, chat_id: int, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM auth_users WHERE chat_id = ? AND user_id = ? LIMIT 1",
            (chat_id, user_id),
        )
        return row is not None

    async def list_auth_users(self, chat_id: int) -> list[int]:
        rows = await self._fetchall(
            "SELECT user_id FROM auth_users WHERE chat_id = ? ORDER BY added_at DESC",
            (chat_id,),
        )
        return [int(row["user_id"]) for row in rows]

    async def set_setting(self, chat_id: int, key: str, value: str | bool | int) -> None:
        await self._execute(
            """
            INSERT INTO chat_settings(chat_id, key, value) VALUES(?, ?, ?)
            ON CONFLICT(chat_id, key) DO UPDATE SET value = excluded.value
            """,
            (chat_id, key, str(value)),
        )

    async def get_setting(self, chat_id: int, key: str, default: str | None = None) -> str | None:
        row = await self._fetchone(
            "SELECT value FROM chat_settings WHERE chat_id = ? AND key = ? LIMIT 1",
            (chat_id, key),
        )
        return str(row["value"]) if row else default

    async def get_bool_setting(self, chat_id: int, key: str, default: bool = False) -> bool:
        value = await self.get_setting(chat_id, key)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "on"}

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None
