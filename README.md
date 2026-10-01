# ShionMusicBot 🎵

A production-grade Telegram **music & video streaming bot** — Pyrogram v2 +
PyTgCalls v3 — with a self-contained MPA PHP web dashboard, built to run on
shared CyberPanel hosting with zero external database dependencies.

<p>
<b>Bot:</b> @ShionMusicBot &nbsp;·&nbsp;
<b>Assistant:</b> @ShionVCAssistant &nbsp;·&nbsp;
<b>Engine:</b> Testweb3 proxy &nbsp;·&nbsp;
<b>Dashboard:</b> <code>/project/telegram/bot/ShionMusicBot/</code>
</p>

---

## ✨ Features

- **Single-source streaming policy** — every YouTube search, metadata fetch and
  media stream resolves **exclusively** through the Testweb3 proxy
  (`YT_API_BASE`), keeping the host IP clean. No yt-dlp, no scrapers.
- **Audio & video** — `/play` (audio-only piping) and `/vplay` (video),
  plus `/playforce` / `/vplayforce` to jump the queue.
- **Smart queue engine** — per-chat queues, loop with counter, real seeking
  (ffmpeg `-ss` re-pipe), shuffle, volume control, inline playback buttons.
- **Zero-DB architecture** — a high-speed in-memory state engine with the
  classic MongoDB-style interface (`get_play_mode`, `is_auth`, `add_auth`,
  `get_admins`, `get_lang`, `is_chat`, `add_chat`, `is_user`, `add_user`, …)
  and JSON snapshot persistence across restarts.
- **Multilingual** — English & हिन्दी, switchable per chat.
- **MPA web dashboard** — Landing, Live Status/Ping console, Command Explorer,
  a manager-key-protected Assistant Login flow (phone → OTP → optional 2FA),
  and a Web Audio Streamer. Session strings are written only to the private
  runtime outside `public_html`.
- **Self-healing** — cron watchdog + `runner.php` control endpoint.

## 📦 Project layout

```
ShionMusicBot/
├── anony/                    # the bot package (python3 -m anony)
│   ├── __main__.py           # boot sequence + status writer
│   ├── core/
│   │   ├── bot.py            # @ShionMusicBot client
│   │   ├── userbot.py        # @ShionVCAssistant client
│   │   ├── calls.py          # PyTgCalls v3 manager
│   │   ├── youtube.py        # Testweb3 engine (search / stream resolve)
│   │   ├── mongo.py          # in-memory state engine (async interface)
│   │   ├── lang.py           # translation service
│   │   └── dir.py            # runtime directories
│   ├── helpers/              # queue, player orchestration, admins, keyboards…
│   ├── locales/              # en.json / hi.json
│   └── plugins/              # 22 command modules
├── config.py                 # .env → typed config
├── index.php                 # dashboard: landing
├── status.php                # dashboard: live status & log console
├── commands.php              # dashboard: command explorer
├── assistant.php             # secure phone/OTP/2FA assistant manager
├── session_auth.py           # private-stdin Telegram login bridge
├── webstream.php             # dashboard: web audio streamer
├── runner.php                # key-protected process control endpoint
├── ensure-running.sh         # PID-safe 1-minute cron watchdog
├── bootstrap.sh              # private venv + bundled ffmpeg installer
├── installer.php             # one-time deployment installer
├── requirements.txt          # py-tgcalls[pyrogram]==3.0.0 stack
├── tests/                    # pytest suite (55 tests)
└── .env.example              # configuration template
```

## 🚀 Commands

| Area | Commands |
|------|----------|
| Streaming | `/play` `/vplay` `/playforce` `/vplayforce` `/pause` `/resume` `/stop` `/end` `/skip` `/seek <1:30>` `/volume <0-200>` |
| Queue | `/queue` `/queue clear` `/shuffle` `/loop <n\|off>` |
| Info | `/start` `/help` `/settings` `/lang <en\|hi>` `/ping` `/alive` `/stats` `/id` |
| Admin | `/auth` `/unauth` `/authusers` |
| Owner & sudo | `/addsudo` `/delsudo` `/sudolist` `/blacklistchat` `/whitelistchat` `/blacklistedchats` `/broadcast` `/restart` `/logs` `/exec` |

## ⚙️ Configuration (`.env`)

See [`.env.example`](.env.example). In production the file is stored at
`~/private/shionmusicbot_runtime/bot.env`, never in the web root. Along with
Telegram and playback settings it contains independent `RUNNER_KEY` and
`SESSION_MANAGER_KEY` secrets. The Assistant Manager atomically replaces
`SESSION1` and `SESSION_STRING` after a successful Telegram login.

## 🧰 Stack

| Layer | Technology |
|-------|------------|
| MTProto | **pyrogrammod** (Pyrogram v2 API fork) via `py-tgcalls[pyrogram]==3.0.0` |
| Group calls | **PyTgCalls v3 / NTgCalls v3** (ffmpeg piping) |
| HTTP | aiohttp |
| State | in-memory engine + JSON snapshots |
| Web | plain MPA PHP (LiteSpeed compatible), inline SVG |

Requires **Python ≥ 3.10**. `bootstrap.sh` installs dependencies into the
private runtime virtualenv and links the `imageio-ffmpeg` bundled binary into
the private runtime `bin/` directory.

## 🛠 Local development

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env       # fill in credentials
venv/bin/python -m pytest  # 55 tests
venv/bin/python -m anony   # run the bot
```

## 🔐 Web endpoints

- `index.php`, `status.php`, `commands.php`, `webstream.php` — public dashboard pages
- `assistant.php` — management actions require the private manager key, CSRF
  token, short-lived secure session cookie and server-side rate limits
- `runner.php` — actions require `X-Runner-Key` (query-key fallback is retained
  for manual diagnostics)
- `.htaccess` denies source, secrets, logs, archives and runtime directories;
  mutable runtime data is additionally kept outside `public_html`

---

Built from level zero with ❤️ — **ShionMusicBot v1.0.0**
