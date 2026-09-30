from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover - optional dependency at runtime
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


ROOT_DIR = Path(__file__).resolve().parents[1]


def _env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and (value is None or str(value).strip() == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip() if isinstance(value, str) else value


def _env_int(name: str, default: int | None = None, *, required: bool = False) -> int | None:
    value = _env(name, None, required=required)
    if value in (None, ""):
        return default
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _env_int_set(name: str) -> set[int]:
    raw = _env(name, "") or ""
    users: set[int] = set()
    for part in raw.replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            users.add(int(part))
        except ValueError as exc:
            raise RuntimeError(f"{name} contains a non-integer value: {part}") from exc
    return users


@dataclass(slots=True)
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    session_string: str | None
    assistant_phone: str | None

    bot_name: str = "Shion Music bot"
    owner_id: int | None = None
    sudo_users: set[int] | None = None
    workdir: Path = ROOT_DIR
    sessions_dir: Path = ROOT_DIR / "sessions"
    downloads_dir: Path = ROOT_DIR / "downloads"
    database_path: Path = ROOT_DIR / "shion.sqlite3"

    command_prefixes: tuple[str, ...] = ("/", "!", ".")
    auto_start_voice_chat: bool = True
    auto_leave_when_queue_empty: bool = True
    admin_only_controls: bool = True
    default_dj_mode: bool = False

    max_duration_seconds: int = 3 * 60 * 60
    playlist_limit: int = 20
    max_file_size_mb: int = 100
    ytdlp_cookie_file: str | None = None
    yt_api_base: str | None = None

    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        owner_id = _env_int("OWNER_ID")
        sudo = _env_int_set("SUDO_USERS")
        if owner_id:
            sudo.add(owner_id)

        settings = cls(
            api_id=_env_int("API_ID", required=True) or 0,
            api_hash=_env("API_HASH", required=True) or "",
            bot_token=_env("BOT_TOKEN", required=True) or "",
            session_string=_env("SESSION_STRING"),
            assistant_phone=_env("ASSISTANT_PHONE"),
            bot_name=_env("BOT_NAME", "Shion Music bot") or "Shion Music bot",
            owner_id=owner_id,
            sudo_users=sudo,
            sessions_dir=Path(_env("SESSIONS_DIR", str(ROOT_DIR / "sessions")) or "sessions"),
            downloads_dir=Path(_env("DOWNLOADS_DIR", str(ROOT_DIR / "downloads")) or "downloads"),
            database_path=Path(
                _env("DATABASE_PATH", str(ROOT_DIR / "shion.sqlite3")) or "shion.sqlite3"
            ),
            auto_start_voice_chat=_env_bool("AUTO_START_VOICE_CHAT", True),
            auto_leave_when_queue_empty=_env_bool("AUTO_LEAVE_WHEN_QUEUE_EMPTY", True),
            admin_only_controls=_env_bool("ADMIN_ONLY_CONTROLS", True),
            default_dj_mode=_env_bool("DEFAULT_DJ_MODE", False),
            max_duration_seconds=_env_int("MAX_DURATION_SECONDS", 3 * 60 * 60) or 3 * 60 * 60,
            playlist_limit=_env_int("PLAYLIST_LIMIT", 20) or 20,
            max_file_size_mb=_env_int("MAX_FILE_SIZE_MB", 100) or 100,
            ytdlp_cookie_file=_env("YTDLP_COOKIE_FILE"),
            yt_api_base=_env("YT_API_BASE"),
            log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        )
        return settings

    def prepare_dirs(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_runtime(self) -> None:
        missing: list[str] = []
        if not self.session_string:
            missing.append("SESSION_STRING")
        if missing:
            raise RuntimeError(
                "Missing runtime secret(s): "
                + ", ".join(missing)
                + ". Run scripts/generate_session.py with the assistant account first."
            )


_CONFIG: Settings | None = None


def get_config() -> Settings:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = Settings.from_env()
        _CONFIG.prepare_dirs()
    return _CONFIG
