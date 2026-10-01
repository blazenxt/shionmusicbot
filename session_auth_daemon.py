#!/usr/bin/env python3
"""Private connected assistant-login daemon.

It keeps one Pyrogram connection alive from send_code through sign_in/2FA so
Telegram's phone-code hash and temporary authorization state never cross a
process or connection boundary.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

from pyrogram.errors import SessionPasswordNeeded

from session_auth import (
    AUTH_DIR,
    DAEMON_PID_FILE,
    SOCKET_FILE,
    START_FILE,
    STATE_FILE,
    cleanup_pending,
    client,
    finalize,
    friendly_error,
    rate_limit,
    read_env,
    write_json,
)

LOCK_FILE = AUTH_DIR / "daemon.lock"


async def run_daemon(phone: str) -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_DIR.chmod(0o700)
    lock_handle = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        write_json(START_FILE, {"ok": False, "error": "Another secure login process is already active."})
        lock_handle.close()
        return

    DAEMON_PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    os.chmod(DAEMON_PID_FILE, 0o600)
    env = read_env()
    app = client(env)
    connected = False
    completed = False
    stop_event = asyncio.Event()
    state: dict[str, Any] = {}

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass

    async def respond(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        writer.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionError):
            pass

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal completed, state
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=15)
            payload = json.loads(raw.decode("utf-8"))
            action = str(payload.get("action", "status"))

            if action == "resend":
                allowed, error = rate_limit("send")
                if not allowed:
                    await respond(writer, {"ok": False, "error": error})
                    return
                sent = await app.send_code(phone)
                state.update(
                    phone_code_hash=sent.phone_code_hash,
                    created_at=int(time.time()),
                    step="code",
                )
                write_json(STATE_FILE, state)
                await respond(writer, {"ok": True, "step": "code"})
                return

            if action == "verify":
                allowed, error = rate_limit("verify")
                if not allowed:
                    await respond(writer, {"ok": False, "error": error})
                    return
                code = re.sub(r"\D", "", str(payload.get("code", "")))
                if not re.fullmatch(r"\d{4,8}", code):
                    await respond(writer, {"ok": False, "error": "Enter the valid code sent by Telegram."})
                    return
                try:
                    await app.sign_in(phone, str(state["phone_code_hash"]), code)
                except SessionPasswordNeeded:
                    state["step"] = "password"
                    write_json(STATE_FILE, state)
                    await respond(writer, {"ok": True, "step": "password"})
                    return
                status = await finalize(app)
                completed = True
                await respond(writer, {"ok": True, "step": "saved", **status})
                stop_event.set()
                return

            if action == "password":
                allowed, error = rate_limit("verify")
                if not allowed:
                    await respond(writer, {"ok": False, "error": error})
                    return
                password = str(payload.get("password", ""))
                if not password:
                    await respond(writer, {"ok": False, "error": "Enter your Telegram two-step verification password."})
                    return
                await app.check_password(password)
                status = await finalize(app)
                completed = True
                await respond(writer, {"ok": True, "step": "saved", **status})
                stop_event.set()
                return

            if action == "reset":
                await respond(writer, {"ok": True, "step": "phone"})
                stop_event.set()
                return

            await respond(writer, {"ok": True, "step": state.get("step", "phone")})
        except Exception as exc:
            try:
                await respond(writer, {"ok": False, "error": friendly_error(exc)})
            except Exception:
                writer.close()

    server: asyncio.AbstractServer | None = None
    try:
        authorized = await app.connect()
        connected = True
        if authorized:
            status = await finalize(app)
            completed = True
            write_json(START_FILE, {"ok": True, "step": "saved", **status})
            return

        sent = await app.send_code(phone)
        state = {
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
            "created_at": int(time.time()),
            "step": "code",
            "daemon_pid": os.getpid(),
        }
        write_json(STATE_FILE, state)
        SOCKET_FILE.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(handle, path=str(SOCKET_FILE))
        os.chmod(SOCKET_FILE, 0o600)
        write_json(START_FILE, {"ok": True, "step": "code"})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=900)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(0.15)
    except Exception as exc:
        write_json(START_FILE, {"ok": False, "error": friendly_error(exc)})
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()
        if connected:
            try:
                await app.disconnect()
            except Exception:
                pass
        cleanup_pending(stop_daemon=False, preserve_start=True)
        LOCK_FILE.unlink(missing_ok=True)
        lock_handle.close()


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        phone = str(payload.get("phone", ""))
        if not re.fullmatch(r"\+\d{7,15}", phone):
            write_json(START_FILE, {"ok": False, "error": "Invalid phone number."})
            return
        asyncio.run(run_daemon(phone))
    except Exception as exc:
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        write_json(START_FILE, {"ok": False, "error": friendly_error(exc)})


if __name__ == "__main__":
    main()
