#!/usr/bin/env bash
# One-minute cron watchdog for ShionMusicBot.
set -u

PROJECT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="${SHION_RUNTIME_DIR:-$HOME/private/shionmusicbot_runtime}"
PY="$RUNTIME/venv/bin/python3"
PIDFILE="$RUNTIME/bot.pid"

mkdir -p "$RUNTIME" "$RUNTIME/data"
exec 9>"$RUNTIME/supervisor.lock"
flock -n 9 || exit 0

if [ -s "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    CWD="$(readlink "/proc/$PID/cwd" 2>/dev/null || true)"
    [ "$CWD" = "$PROJECT" ] && exit 0
  fi
  rm -f "$PIDFILE"
fi

[ -x "$PY" ] || exit 0
[ -f "$RUNTIME/.bootstrapped" ] || exit 0

cd "$PROJECT" || exit 1
export SHION_RUNTIME_DIR="$RUNTIME"
export PATH="$RUNTIME/bin:$PATH"
nohup "$PY" -m anony >> "$RUNTIME/bot.log" 2>&1 < /dev/null &
echo $! > "$PIDFILE"
printf '%s watchdog started pid %s\n' "$(date '+%F %T')" "$!" >> "$RUNTIME/supervisor.log"
