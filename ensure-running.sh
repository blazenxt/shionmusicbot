#!/usr/bin/env bash
# ShionMusicBot watchdog — designed for a 1-minute cron job.
# Starts the daemon only when it is not already running.
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
mkdir -p data

# one instance of the watchdog at a time
exec 9>"data/ensure.lock"
flock -n 9 || exit 0

if pgrep -f -- "-m anony" >/dev/null 2>&1; then
    exit 0
fi

# never start before dependencies are ready
[ -f .bootstrapped ] || exit 0

export PATH="$DIR/bin:$PATH"

PY="$DIR/venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

nohup "$PY" -m anony >> data/nohup.log 2>&1 &
echo "$(date '+%F %T') watchdog: started bot (pid $!)" >> data/watchdog.log
