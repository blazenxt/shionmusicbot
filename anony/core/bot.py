"""Pyrogram bot client with boot-time logging."""

from __future__ import annotations

import logging

from pyrogram import Client, enums

from config import BASE_DIR, config

log = logging.getLogger(__name__)


class Bot(Client):
    """The @ShionMusicBot Telegram client.

    Plugins auto-load from :mod:`anony.plugins` when the client starts.
    Markdown is the default parse mode; ``reply_*`` calls therefore never
    pass the unsupported ``quote`` kwarg (Pyrogram v2 semantics).
    """

    # pytgcalls detects the MTProto flavour via ``Client.__class__.__module__``;
    # our subclass lives in the anony package, so re-point the tag to keep
    # PyTgCalls' bridged client detection happy.
    __module__ = "pyrogram.client"

    def __init__(self) -> None:
        super().__init__(
            name="ShionMusicBot",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            plugins=dict(root="anony.plugins"),
            workers=config.WORKERS,
            parse_mode=enums.ParseMode.MARKDOWN,
            sleep_threshold=20,
            workdir=str(BASE_DIR),
        )

    async def start(self) -> None:
        await super().start()
        me = await self.get_me()
        self.id = me.id
        self.username = me.username or config.BOT_USERNAME
        self.mention = me.first_name or "Shion"
        log.info("Bot started as @%s [ID: %s]", me.username, me.id)

    async def stop(self, *args) -> None:  # noqa: ANN002
        try:
            await super().stop()
        finally:
            log.info("Bot stopped.")
