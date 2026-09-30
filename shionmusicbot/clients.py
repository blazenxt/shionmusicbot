from __future__ import annotations

from pyrogram import Client
from pytgcalls import PyTgCalls

from .config import get_config
from .database import Database
from .downloader import Downloader
from .player import Player

CONFIG = get_config()

bot = Client(
    "shion_bot",
    api_id=CONFIG.api_id,
    api_hash=CONFIG.api_hash,
    bot_token=CONFIG.bot_token,
    workdir=str(CONFIG.sessions_dir),
    sleep_threshold=60,
)

assistant = Client(
    "shion_assistant",
    api_id=CONFIG.api_id,
    api_hash=CONFIG.api_hash,
    session_string=CONFIG.session_string,
    workdir=str(CONFIG.sessions_dir),
    sleep_threshold=60,
)

calls = PyTgCalls(assistant)

db = Database(CONFIG.database_path)

downloader = Downloader(
    CONFIG.downloads_dir,
    max_duration_seconds=CONFIG.max_duration_seconds,
    max_file_size_mb=CONFIG.max_file_size_mb,
    playlist_limit=CONFIG.playlist_limit,
    cookie_file=CONFIG.ytdlp_cookie_file,
    yt_api_base=CONFIG.yt_api_base,
)

player = Player(bot, calls, db, CONFIG)
