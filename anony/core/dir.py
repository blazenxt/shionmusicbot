"""Private runtime paths used by the bot and web dashboard."""

from __future__ import annotations

from pathlib import Path

from config import PROJECT_DIR, RUNTIME_DIR

ROOT: Path = PROJECT_DIR
RUNTIME: Path = RUNTIME_DIR
CACHE: Path = RUNTIME / "cache"
DOWNLOADS: Path = RUNTIME / "downloads"
DATA: Path = RUNTIME / "data"
LOG_FILE: Path = RUNTIME / "bot.log"
WEB_STATUS: Path = RUNTIME / "web_status.json"
SESSION_REQUIRED: Path = RUNTIME / "SESSION_REQUIRED"
PID_FILE: Path = RUNTIME / "bot.pid"


def ensure_dirs() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for path in (CACHE, DOWNLOADS, DATA, RUNTIME / "sessions", RUNTIME / "auth"):
        path.mkdir(parents=True, exist_ok=True)
    try:
        RUNTIME.chmod(0o700)
    except OSError:
        pass


def project_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)
