#!/usr/bin/env bash
# Idempotent production bootstrap. Secrets and dependencies stay outside public_html.
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="${SHION_RUNTIME_DIR:-$HOME/private/shionmusicbot_runtime}"
VENV="$RUNTIME/venv"
LOG="$RUNTIME/install.log"

mkdir -p "$RUNTIME" "$RUNTIME/bin" "$RUNTIME/data" "$RUNTIME/cache" \
  "$RUNTIME/downloads" "$RUNTIME/sessions" "$RUNTIME/auth"
chmod 700 "$RUNTIME" "$RUNTIME/auth" "$RUNTIME/sessions" 2>/dev/null || true
[ -f "$RUNTIME/bot.env" ] && chmod 600 "$RUNTIME/bot.env" || true

touch "$LOG"
say() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

say "bootstrap start"
if [ ! -x "$VENV/bin/python3" ]; then
  say "creating private virtualenv"
  python3 -m venv "$VENV"
fi

say "upgrading packaging tools"
"$VENV/bin/python3" -m pip install --upgrade pip wheel setuptools >>"$LOG" 2>&1

# Keep the install manifest private so production can remove the public copy.
if [ -f "$PROJECT/requirements.txt" ]; then
  cp "$PROJECT/requirements.txt" "$RUNTIME/requirements.txt"
  chmod 600 "$RUNTIME/requirements.txt" 2>/dev/null || true
fi
if [ ! -f "$RUNTIME/requirements.txt" ]; then
  say "ERROR: requirements manifest is missing"
  exit 1
fi
say "installing production requirements"
"$VENV/bin/python3" -m pip install --upgrade -r "$RUNTIME/requirements.txt" >>"$LOG" 2>&1

say "linking bundled ffmpeg"
FFMPEG="$($VENV/bin/python3 - <<'PY'
import imageio_ffmpeg
print(imageio_ffmpeg.get_ffmpeg_exe())
PY
)"
if [ -x "$FFMPEG" ]; then
  ln -sfn "$FFMPEG" "$RUNTIME/bin/ffmpeg"
  chmod +x "$FFMPEG" "$RUNTIME/bin/ffmpeg" 2>/dev/null || true
else
  say "ERROR: bundled ffmpeg not found"
  exit 1
fi

say "running import smoke test"
(
  cd "$PROJECT"
  export SHION_RUNTIME_DIR="$RUNTIME"
  export PATH="$RUNTIME/bin:$PATH"
  "$VENV/bin/python3" -c 'import pyrogram, pytgcalls, ntgcalls, aiohttp, anony; print("imports OK")'
) >>"$LOG" 2>&1

chmod +x "$PROJECT/ensure-running.sh" "$PROJECT/bootstrap.sh" "$PROJECT/cron_guard.sh" 2>/dev/null || true
touch "$RUNTIME/.bootstrapped"
say "bootstrap complete: $($VENV/bin/python3 -V 2>&1); $($RUNTIME/bin/ffmpeg -version 2>/dev/null | head -1)"
