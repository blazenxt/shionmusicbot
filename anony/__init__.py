"""ShionMusicBot — global runtime singletons.

Importing this package constructs (but never *starts*) every runtime
component: the bot client, the assistant userbot, the PyTgCalls engine,
the in-memory database and the translation service.  The boot sequence
lives in :mod:`anony.__main__`.
"""

import time

from anony.core.bot import Bot
from anony.core.calls import TgCall
from anony.core.lang import Lang
from anony.core.mongo import DB
from anony.core.userbot import Userbot
from config import config

__version__ = "1.0.0"

#: Process boot timestamp (uptime reference for /ping, /stats, dashboard).
BOOT_TIME = time.time()

__all__ = [
    "__version__",
    "config",
    "db",
    "lang",
    "bot",
    "userbot",
    "call",
]

# High-speed, zero-external-dependency state engine.
db = DB()

# Multilingual translation service (en / hi …).
lang = Lang(db)

# The Telegram bot itself (plugins auto-load from anony/plugins).
bot = Bot()

# Assistant userbot used to join and stream into voice chats.
userbot = Userbot()

# PyTgCalls v3 voice-chat streaming manager.
call = TgCall(userbot)
