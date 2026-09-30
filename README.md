# Shion Music bot

Open-source Telegram voice chat music bot for **Shion Music bot**.

Maintainer / author: **@blazenxt**  
Author email for commits/releases: **m11.galaxy.m581@gmail.com**

## Features

- Telegram group voice chat streaming with an assistant user account
- YouTube search and URL playback through `yt-dlp`
- Direct audio/radio stream URL playback
- Telegram replied audio/video/document playback
- Queue, playlist, shuffle, loop, seek, volume
- Pause, resume, skip, stop, join, leave
- Admin/DJ authorization system with SQLite storage
- Inline control buttons
- Dockerfile, docker-compose, CI workflow

## Important Telegram limitation

Telegram Bot API bots cannot directly join voice chats. This project uses two clients:

1. **Bot account** — handles commands like `/play`, `/skip`, `/pause`.
2. **Assistant user account** — joins the voice chat and streams audio.

Add both the bot and assistant account to your group. The assistant should be an admin or at least allowed to join/speak in voice chat.

## Requirements

- Python 3.10+
- FFmpeg and FFprobe installed on the server
- Telegram `API_ID` and `API_HASH` from <https://my.telegram.org>
- Bot token from [@BotFather](https://t.me/BotFather)
- Pyrogram session string for the assistant account

## Quick setup

```bash
git clone https://github.com/blazenxt/shionmusicbot.git
cd shionmusicbot

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
nano .env
```

Install FFmpeg on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

## Generate assistant session string

Fill `API_ID`, `API_HASH`, and `ASSISTANT_PHONE` in `.env`, then run:

```bash
python scripts/generate_session.py
```

Telegram will send an OTP to the assistant phone number. Paste the generated value into `.env`:

```env
SESSION_STRING="..."
```

Never commit `.env`, `SESSION_STRING`, bot token, API hash, cookies, or server passwords.

## Run

```bash
python -m shionmusicbot
```

With Docker:

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

## Commands

### Music

- `/play song name` — play from YouTube search
- `/play YouTube/link` — play URL
- `/play` — play replied audio/video/document
- `/playforce query` or `/fplay query` — clear current queue and play now
- `/playlist playlist-link` — add playlist/search results
- `/playlist` as reply to newline-separated song list
- `/radio direct-stream-url` — play live radio/direct stream
- `/queue` — show queue
- `/now` — show current track

### Controls

- `/pause`
- `/resume`
- `/skip` or `/skip 3`
- `/stop` or `/end`
- `/seek 1:20`
- `/volume 1-200`
- `/loop off|one|queue`
- `/shuffle`
- `/join`
- `/leave`

### Admin / DJ

- `/auth` reply to user or `/auth @username`
- `/unauth` reply to user or `/unauth @username`
- `/authusers`
- `/dj on|off`
- `/settings`

## Environment variables

See [`.env.example`](.env.example) for all config values.

Required:

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `SESSION_STRING`

Optional:

- `OWNER_ID`, `SUDO_USERS`
- `YT_API_BASE` for a custom extractor endpoint
- `YTDLP_COOKIE_FILE` for yt-dlp cookies
- `MAX_DURATION_SECONDS`, `PLAYLIST_LIMIT`, `MAX_FILE_SIZE_MB`

## Deployment notes

For stable Telegram voice chat streaming, use a real VPS with shell access. SFTP-only web hosting usually cannot keep a Python voice chat process running 24/7 or install system packages like FFmpeg.

Recommended process manager:

```bash
sudo apt install -y tmux ffmpeg
# or use systemd / docker compose
```

## CI

GitHub Actions runs:

- Ruff lint
- Python compile check
- Unit tests for utility functions

## License

MIT License. See [LICENSE](LICENSE).
