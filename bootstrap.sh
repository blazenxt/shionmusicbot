#!/usr/bin/env bash
# ShionMusicBot dependency bootstrap (idempotent).
#   • python venv (fallback: pip --user)
#   • pinned requirements
#   • optional tgcrypto accelerator
#   • static ffmpeg + ffprobe into ./bin (PyTgCalls v3 pipes media via ffmpeg)
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
LOG="install.log"

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

say "── bootstrap start ──"

# ── 1. python environment ────────────────────────────────────────────
USE_VENV=0
if [ ! -x venv/bin/python3 ]; then
    say "creating virtualenv…"
    if python3 -m venv venv >>"$LOG" 2>&1; then
        USE_VENV=1
    else
        say "venv creation failed — falling back to pip --user"
    fi
else
    USE_VENV=1
fi

if [ "$USE_VENV" = "1" ]; then
    say "upgrading pip/wheel…"
    venv/bin/pip install --upgrade pip wheel >>"$LOG" 2>&1
    say "installing requirements (venv)…"
    if ! venv/bin/pip install -r requirements.txt >>"$LOG" 2>&1; then
        say "requirements install FAILED (venv)"
        exit 1
    fi
    venv/bin/pip install tgcrypto >>"$LOG" 2>&1 || say "tgcrypto skipped (optional)"
    PYE="$DIR/venv/bin/python3"
else
    say "upgrading pip/wheel (user)…"
    pip3 install --user --upgrade pip wheel >>"$LOG" 2>&1
    say "installing requirements (user)…"
    if ! pip3 install --user -r requirements.txt >>"$LOG" 2>&1; then
        say "requirements install FAILED (user)"
        exit 1
    fi
    pip3 install --user tgcrypto >>"$LOG" 2>&1 || say "tgcrypto skipped (optional)"
    PYE="python3"
fi

# ── 2. ffmpeg ─────────────────────────────────────────────────────────
export PATH="$DIR/bin:$PATH"
if ! command -v ffmpeg >/dev/null 2>&1; then
    say "ffmpeg missing — fetching static build…"
    mkdir -p bin tmp_dl
    ok=0
    if curl -fsSL -o tmp_dl/ffmpeg.tar.xz \
        "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz" >>"$LOG" 2>&1; then
        if tar -xJf tmp_dl/ffmpeg.tar.xz -C tmp_dl >>"$LOG" 2>&1; then
            FFBIN="$(find tmp_dl -type f -name ffmpeg -perm -u+x | head -1)"
            FFPROBE="$(find tmp_dl -type f -name ffprobe -perm -u+x | head -1)"
            if [ -n "$FFBIN" ]; then
                cp "$FFBIN" bin/ffmpeg; [ -n "$FFPROBE" ] && cp "$FFPROBE" bin/ffprobe
                chmod +x bin/ffmpeg bin/ffprobe 2>/dev/null; ok=1
            fi
        fi
    fi
    if [ "$ok" != "1" ]; then
        say "primary ffmpeg download failed — trying mirror…"
        if curl -fsSL -o tmp_dl/ffmpeg.tar.xz \
            "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" >>"$LOG" 2>&1 \
            && tar -xJf tmp_dl/ffmpeg.tar.xz -C tmp_dl >>"$LOG" 2>&1; then
            FFBIN="$(find tmp_dl -type f -name ffmpeg -perm -u+x | head -1)"
            FFPROBE="$(find tmp_dl -type f -name ffprobe -perm -u+x | head -1)"
            if [ -n "$FFBIN" ]; then
                cp "$FFBIN" bin/ffmpeg; [ -n "$FFPROBE" ] && cp "$FFPROBE" bin/ffprobe
                chmod +x bin/ffmpeg bin/ffprobe 2>/dev/null; ok=1
            fi
        fi
    fi
    rm -rf tmp_dl
    [ "$ok" = "1" ] && say "ffmpeg installed: $(./bin/ffmpeg -version 2>/dev/null | head -1)" \
                     || say "WARNING: ffmpeg could not be installed — playback will fail"
else
    say "system ffmpeg found: $(command -v ffmpeg)"
fi

# ── 3. smoke test ─────────────────────────────────────────────────────
if "$PYE" -c "import anony" >>"$LOG" 2>&1; then
    say "import smoke test OK"
else
    say "import smoke test FAILED — check install.log"
    exit 1
fi

touch .bootstrapped
say "── bootstrap complete ──"
