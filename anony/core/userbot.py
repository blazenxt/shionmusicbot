"""Assistant Pyrogram client (voice-chat streaming account)."""

from __future__ import annotations

import logging
from typing import Optional

from pyrogram import Client, enums

from config import BASE_DIR, config

log = logging.getLogger(__name__)


class Userbot(Client):
    """The @ShionVCAssistant userbot that joins group voice chats.

    Uses the Pyrogram v2 session string from ``SESSION1`` /
    ``SESSION_STRING``.  If no session is configured (e.g. inside the
    test environment) the client still constructs, but ``start()``
    becomes a no-op so imports never explode.
    """

    # keep PyTgCalls' flavour detection working (see anony/core/bot.py)
    __module__ = "pyrogram.client"

    def __init__(
        self,
        session_string: Optional[str] = None,
        index: int = 1,
    ) -> None:
        self.index = index
        self._me = None
        super().__init__(
            name=f"assistant{index}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=session_string or config.assistant_session or None,
            in_memory=True,
            parse_mode=enums.ParseMode.MARKDOWN,
            workdir=str(BASE_DIR),
        )

    async def start(self):
        if not config.assistant_session:
            log.warning(
                "Assistant %d has no session string — voice chats disabled "
                "(set SESSION1 in .env).",
                self.index,
            )
            return None
        await super().start()
        self._me = await self.get_me()
        log.info(
            "Assistant %d started as @%s [ID: %s]",
            self.index,
            self._me.username,
            self._me.id,
        )
        return self._me

    async def stop(self, *args) -> None:  # noqa: ANN002
        if not self.is_connected:
            return
        try:
            await super().stop()
        finally:
            log.info("Assistant %d stopped.", self.index)
