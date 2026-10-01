#!/usr/bin/env bash
# One-minute cron watchdog for ShionMusicBot.
set -u

PROJECT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="${SHION_RUNTIME_DIR:-$HOME/private/shionmusicbot_runtime}"
VENV_PY="$RUNTIME/venv/bin/python3"
PY="$RUNTIME/bin/python-safe"
[ -x "$PY" ] || PY="$VENV_PY"
PIDFILE="$RUNTIME/bot.pid"

mkdir -p "$RUNTIME" "$RUNTIME/data"

# Start the defensive cron/public-artifact guard first. It has its own lock and
# is restarted here if a stale deployment process terminates it.
GUARD="$PROJECT/cron_guard.sh"
GUARD_PIDFILE="$RUNTIME/cron_guard.pid"
GUARD_OK=0
if [ -s "$GUARD_PIDFILE" ]; then
  GUARD_PID="$(cat "$GUARD_PIDFILE" 2>/dev/null || true)"
  if [[ "$GUARD_PID" =~ ^[0-9]+$ ]] && kill -0 "$GUARD_PID" 2>/dev/null; then
    case "$(tr '\0' ' ' < "/proc/$GUARD_PID/cmdline" 2>/dev/null || true)" in
      *cron_guard.sh*) GUARD_OK=1 ;;
    esac
  fi
fi
if [ "$GUARD_OK" != "1" ] && [ -f "$GUARD" ]; then
  rm -f "$GUARD_PIDFILE"
  nohup /bin/bash "$GUARD" >/dev/null 2>&1 < /dev/null &
  echo $! > "$GUARD_PIDFILE"
fi

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
