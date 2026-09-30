from __future__ import annotations

import asyncio
import logging

from pyrogram import idle

from .clients import CONFIG, assistant, bot, calls, db, player
from .logger import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging(CONFIG.log_level)
    CONFIG.validate_runtime()

    # Import handlers only after clients are created; decorators register on import.
    from . import handlers as _handlers  # noqa: F401

    await db.setup()
    player.register_call_handlers()

    logger.info("Starting assistant user client...")
    await assistant.start()
    assistant_me = await assistant.get_me()
    logger.info("Assistant logged in as %s (%s)", assistant_me.first_name, assistant_me.id)

    logger.info("Starting bot client...")
    await bot.start()
    bot_me = await bot.get_me()
    logger.info("Bot started as @%s (%s)", bot_me.username, bot_me.id)

    logger.info("Starting PyTgCalls...")
    await calls.start()
    logger.info("Shion Music bot is ready.")

    try:
        await idle()
    finally:
        logger.info("Stopping Shion Music bot...")
        await db.close()
        for client in (bot, assistant):
            try:
                await client.stop()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
