"""Runtime directories — auto-created at import/boot time.

All paths are anchored to the project root (the parent of the ``anony``
package), never to the current working directory, so behaviour is
identical whether the bot is started from a shell, ``runner.php`` or a
cron watchdog.
"""

from __future__ import annotations

import os
from pathlib import Path

# ShionMusicBot/
ROOT: Path = Path(__file__).resolve().parent.parent.parent

# Runtime directories
CACHE: Path = ROOT / "cache"        # thumbnails & temporary media
DOWNLOADS: Path = ROOT / "downloads"  # fallback downloaded streams
DATA: Path = ROOT / "data"          # persistent state (state.json, plays.log)

# Files
LOG_FILE: Path = ROOT / "bot.log"
WEB_STATUS: Path = ROOT / "web_status.json"


def ensure_dirs() -> None:
    """Create every runtime directory if missing (idempotent)."""
    for path in (CACHE, DOWNLOADS, DATA):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def project_path(*parts: str) -> Path:
    """Return an absolute path inside the project root."""
    return ROOT.joinpath(*parts)
