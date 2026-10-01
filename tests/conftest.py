"""Test bootstrap — project root on sys.path + safe env defaults.

Runs before any project import so a fresh clone (no .env) still boots.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("API_ID", "12345678")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST-token-for-imports")
os.environ.setdefault("BOT_USERNAME", "ShionMusicBot")
os.environ.setdefault("OWNER_ID", "7330774855")
os.environ.setdefault("OWNER_USERNAME", "zucms")
os.environ.setdefault("SESSION1", "TESTSESSION-DUMMY")
os.environ.setdefault("SESSION_STRING", "TESTSESSION-DUMMY")
os.environ.setdefault("ASSISTANT_ID", "8292016026")
os.environ.setdefault("ASSISTANT_USERNAME", "ShionVCAssistant")
os.environ.setdefault("SUPPORT_CHANNEL", "https://t.me/zucms")
os.environ.setdefault("SUPPORT_CHAT", "https://t.me/zucms")
os.environ.setdefault("YT_API_BASE", "http://Testweb3.cstsc.in/yt/")
os.environ.setdefault("DURATION_LIMIT", "60")
os.environ.setdefault("QUEUE_LIMIT", "20")
os.environ.setdefault("PLAYLIST_LIMIT", "20")
os.environ.setdefault("AUTO_LEAVE", "False")
os.environ.setdefault("AUTO_END", "False")
os.environ.setdefault("THUMB_GEN", "False")
os.environ.setdefault("VIDEO_PLAY", "True")
os.environ.setdefault("LANG_CODE", "en")
os.environ.setdefault("WORKERS", "4")
