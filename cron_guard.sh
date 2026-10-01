#!/usr/bin/env bash
# Defensive guard for concurrent/stale deployment jobs on shared CyberPanel.
# Keeps the one approved Shion watchdog cron and removes all other cron lines
# that touch this project/runtime. It also deletes known public debug artefacts.
set -u

PROJECT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="${SHION_RUNTIME_DIR:-$HOME/private/shionmusicbot_runtime}"
LOG="$RUNTIME/cron_guard.log"
LOCK="$RUNTIME/cron_guard.lock"
APPROVED="* * * * * /bin/bash $RUNTIME/ensure_bot.sh >/dev/null 2>&1"

mkdir -p "$RUNTIME"
exec 8>"$LOCK"
flock -n 8 || exit 0

guard_once() {
  local current filtered panel_output python

  # CyberPanel installations may ship a non-setuid crontab binary. Use the
  # authenticated panel endpoint as the primary remover in that environment.
  python="$RUNTIME/venv/bin/python3"
  [ -x "$python" ] || python="$(command -v python3)"
  if [ -f "$RUNTIME/panel_guard.json" ] && [ -f "$PROJECT/panel_cron_guard.py" ]; then
    panel_output="$(SHION_RUNTIME_DIR="$RUNTIME" "$python" "$PROJECT/panel_cron_guard.py" 2>&1 || true)"
    if [ -n "$panel_output" ]; then
      printf '[%s] %s\n' "$(date '+%F %T')" "$panel_output" >>"$LOG"
    fi
  fi

  # Direct crontab access is a cheap fallback on hosts where it is available.
  current="$(mktemp "$RUNTIME/cron.current.XXXXXX")" || return
  filtered="$(mktemp "$RUNTIME/cron.filtered.XXXXXX")" || { rm -f "$current"; return; }

  crontab -l >"$current" 2>/dev/null || true
  awk -v project="$PROJECT" -v runtime="$RUNTIME" -v approved="$APPROVED" '
    $0 == approved { print; next }
    index($0, project) || index($0, runtime) || index($0, "shion_alive") { next }
    { print }
  ' "$current" >"$filtered"

  if ! cmp -s "$current" "$filtered"; then
    if crontab "$filtered" 2>>"$LOG"; then
      printf '[%s] removed unapproved Shion cron entries\n' "$(date '+%F %T')" >>"$LOG"
    fi
  fi
  rm -f "$current" "$filtered"

  # The production tree intentionally has no root-level text files or local
  # environment/venv. These names are artefacts from old debug deployers.
  find "$PROJECT" -maxdepth 1 -type f -name '*.txt' -delete 2>/dev/null || true
  rm -f "$PROJECT/.env" "$PROJECT/.env.b64" 2>/dev/null || true
  rm -rf "$PROJECT/bin" "$PROJECT/venv" "$PROJECT/__pycache__" 2>/dev/null || true

  if [ -f "$LOG" ] && [ "$(wc -c <"$LOG" 2>/dev/null || echo 0)" -gt 200000 ]; then
    tail -n 500 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
}

while :; do
  guard_once
  sleep 3
done
