#!/usr/bin/env python3
"""Private CLI bridge used by assistant.php for Telegram login.

The request arrives as JSON on stdin so phone codes/passwords never appear in
process arguments. Output is one small JSON object and never contains the
exported session string.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded

from config import ENV_FILE, RUNTIME_DIR

AUTH_DIR = RUNTIME_DIR / "auth"
STATE_FILE = AUTH_DIR / "pending.json"
RATE_FILE = AUTH_DIR / "rate.json"
SESSION_NAME = "assistant_login"
SOCKET_FILE = AUTH_DIR / "assistant-auth.sock"
START_FILE = AUTH_DIR / "daemon-start.json"
DAEMON_PID_FILE = AUTH_DIR / "daemon.pid"
DAEMON_SCRIPT = Path(__file__).with_name("session_auth_daemon.py")


def reply(ok: bool, **data: Any) -> None:
    payload = {"ok": ok, **data}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError, TypeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        raw = line.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def update_env(changes: dict[str, str]) -> None:
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in changes:
                output.append(f"{key}={changes[key]}")
                seen.add(key)
                continue
        output.append(line)
    for key, value in changes.items():
        if key not in seen:
            output.append(f"{key}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_FILE)


def cleanup_pending(*, stop_daemon: bool = True, preserve_start: bool = False) -> None:
    if stop_daemon:
        try:
            pid = int(DAEMON_PID_FILE.read_text(encoding="utf-8").strip())
            if pid > 1:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.25)
        except (OSError, ValueError):
            pass
    paths = [STATE_FILE, SOCKET_FILE, DAEMON_PID_FILE]
    if not preserve_start:
        paths.append(START_FILE)
    for path in paths:
        path.unlink(missing_ok=True)
    for suffix in (".session", ".session-journal"):
        (AUTH_DIR / f"{SESSION_NAME}{suffix}").unlink(missing_ok=True)


def rate_limit(action: str) -> tuple[bool, str]:
    now = int(time.time())
    data = read_json(RATE_FILE, {})
    sends = [int(x) for x in data.get("sends", []) if now - int(x) < 3600]
    attempts = [int(x) for x in data.get("attempts", []) if now - int(x) < 900]
    if action == "send":
        if sends and now - sends[-1] < 45:
            return False, f"Please wait {45 - (now - sends[-1])} seconds before requesting another code."
        if len(sends) >= 5:
            return False, "Too many login-code requests. Try again in one hour."
        sends.append(now)
    else:
        if len(attempts) >= 15:
            return False, "Too many verification attempts. Try again in 15 minutes."
        attempts.append(now)
    write_json(RATE_FILE, {"sends": sends, "attempts": attempts})
    return True, ""


def client(env: dict[str, str]) -> Client:
    return Client(
        SESSION_NAME,
        api_id=int(env.get("API_ID", "0")),
        api_hash=env.get("API_HASH", ""),
        workdir=str(AUTH_DIR),
        no_updates=True,
        device_model="Shion Session Manager",
        app_version="2.0",
    )


def friendly_error(exc: BaseException) -> str:
    messages = {
        "PhoneNumberInvalid": "The phone number is invalid.",
        "PhoneNumberBanned": "Telegram has banned this phone number.",
        "PhoneCodeInvalid": "The Telegram login code is incorrect. Use the newest code.",
        "PhoneCodeExpired": "The Telegram login code expired. Press Send another code and use only the newest code.",
        "PasswordHashInvalid": "The two-step verification password is incorrect.",
        "FloodWait": "Telegram rate-limited this login. Please wait and try again.",
    }
    name = type(exc).__name__
    return messages.get(name, f"Telegram login failed ({name}).")


def daemon_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Send one JSON request to the connected private auth daemon."""
    try:
        raw_pid = DAEMON_PID_FILE.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
        os.kill(pid, 0)
        if not SOCKET_FILE.exists():
            raise OSError("auth socket missing")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(90)
            sock.connect(str(SOCKET_FILE))
            sock.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
            chunks = bytearray()
            while b"\n" not in chunks and len(chunks) < 65536:
                part = sock.recv(4096)
                if not part:
                    break
                chunks.extend(part)
        answer = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
        return answer if isinstance(answer, dict) else {"ok": False, "error": "Invalid auth-daemon response."}
    except (OSError, ValueError, json.JSONDecodeError):
        cleanup_pending()
        return {"ok": False, "error": "The secure login process ended. Start again to request a fresh code."}


def start_auth_daemon(payload: dict[str, Any]) -> dict[str, Any]:
    phone = re.sub(r"[\s()-]", "", str(payload.get("phone", "")))
    if not re.fullmatch(r"\+\d{7,15}", phone):
        return {"ok": False, "error": "Use international format, for example +919876543210."}
    allowed, error = rate_limit("send")
    if not allowed:
        return {"ok": False, "error": error}

    cleanup_pending()
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = (AUTH_DIR / "daemon.log").open("ab")
    try:
        process = subprocess.Popen(
            [sys.executable, str(DAEMON_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
            cwd=str(Path(__file__).resolve().parent),
            env={**os.environ, "SHION_RUNTIME_DIR": str(RUNTIME_DIR)},
        )
        assert process.stdin is not None
        process.stdin.write(json.dumps({"phone": phone}, separators=(",", ":")).encode())
        process.stdin.close()
    except (OSError, AssertionError):
        log_handle.close()
        cleanup_pending()
        return {"ok": False, "error": "Could not start the secure Telegram login process."}
    finally:
        try:
            log_handle.close()
        except OSError:
            pass

    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        data = read_json(START_FILE, None)
        if isinstance(data, dict):
            START_FILE.unlink(missing_ok=True)
            return data
        if process.poll() is not None:
            break
        time.sleep(0.2)
    cleanup_pending()
    return {"ok": False, "error": "Telegram did not start the secure login process in time."}


async def finalize(app: Client) -> dict[str, Any]:
    me = await app.get_me()
    session = await app.export_session_string()
    username = me.username or ""
    update_env(
        {
            "SESSION1": session,
            "SESSION_STRING": session,
            "ASSISTANT_ID": str(me.id),
            "ASSISTANT_USERNAME": username,
        }
    )
    (RUNTIME_DIR / "SESSION_REQUIRED").unlink(missing_ok=True)
    status = {
        "assistant_id": me.id,
        "assistant_username": username,
        "assistant_name": " ".join(x for x in (me.first_name, me.last_name) if x),
        "saved_at": int(time.time()),
    }
    write_json(RUNTIME_DIR / "session_status.json", status)
    return status


async def send_code(payload: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    phone = re.sub(r"[\s()-]", "", str(payload.get("phone", "")))
    if not re.fullmatch(r"\+\d{7,15}", phone):
        return {"ok": False, "error": "Use international format, for example +919876543210."}
    allowed, error = rate_limit("send")
    if not allowed:
        return {"ok": False, "error": error}

    cleanup_pending()
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    app = client(env)
    connected = False
    try:
        authorized = await app.connect()
        connected = True
        if authorized:
            status = await finalize(app)
            return {"ok": True, "step": "saved", **status}
        sent = await app.send_code(phone)
        write_json(
            STATE_FILE,
            {
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "created_at": int(time.time()),
                "step": "code",
            },
        )
        delivery = type(sent.type).__name__.replace("SentCodeType", "").lower()
        return {"ok": True, "step": "code", "delivery": delivery}
    finally:
        if connected:
            await app.disconnect()


async def resend_code(env: dict[str, str]) -> dict[str, Any]:
    """Invalidate the previous code and send a fresh one to the same phone."""
    state = read_json(STATE_FILE, {})
    phone = str(state.get("phone", ""))
    if not re.fullmatch(r"\+\d{7,15}", phone):
        cleanup_pending()
        return {"ok": False, "error": "Login request is missing. Start again with the phone number."}
    return await send_code({"phone": phone}, env)


async def verify_code(payload: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    allowed, error = rate_limit("verify")
    if not allowed:
        return {"ok": False, "error": error}
    state = read_json(STATE_FILE, {})
    if int(time.time()) - int(state.get("created_at", 0)) > 900:
        cleanup_pending()
        return {"ok": False, "error": "Login request expired. Request a new code."}
    phone = str(state.get("phone", ""))
    code_hash = str(state.get("phone_code_hash", ""))
    code = re.sub(r"\D", "", str(payload.get("code", "")))
    if not phone or not code_hash or not re.fullmatch(r"\d{4,8}", code):
        return {"ok": False, "error": "Enter the valid code sent by Telegram."}

    app = client(env)
    connected = False
    success = False
    try:
        authorized = await app.connect()
        connected = True
        if not authorized:
            try:
                await app.sign_in(phone, code_hash, code)
            except SessionPasswordNeeded:
                state["step"] = "password"
                write_json(STATE_FILE, state)
                return {"ok": True, "step": "password"}
        status = await finalize(app)
        success = True
        return {"ok": True, "step": "saved", **status}
    finally:
        if connected:
            await app.disconnect()
        if success:
            cleanup_pending()


async def verify_password(payload: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    allowed, error = rate_limit("verify")
    if not allowed:
        return {"ok": False, "error": error}
    state = read_json(STATE_FILE, {})
    if state.get("step") != "password" or int(time.time()) - int(state.get("created_at", 0)) > 900:
        cleanup_pending()
        return {"ok": False, "error": "Login request expired. Request a new code."}
    password = str(payload.get("password", ""))
    if not password:
        return {"ok": False, "error": "Enter your Telegram two-step verification password."}

    app = client(env)
    connected = False
    success = False
    try:
        await app.connect()
        connected = True
        await app.check_password(password)
        status = await finalize(app)
        success = True
        return {"ok": True, "step": "saved", **status}
    finally:
        if connected:
            await app.disconnect()
        if success:
            cleanup_pending()


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        AUTH_DIR.chmod(0o700)
    except OSError:
        pass
    env = read_env()
    if int(env.get("API_ID", "0") or 0) <= 0 or len(env.get("API_HASH", "")) < 32:
        return {"ok": False, "error": "Telegram API_ID/API_HASH are not configured on the server."}
    action = str(payload.get("action", "status"))
    if action == "send":
        return start_auth_daemon(payload)
    if action in {"resend", "verify", "password"}:
        return daemon_request(payload)
    if action == "reset":
        result = daemon_request(payload) if SOCKET_FILE.exists() else {"ok": True, "step": "phone"}
        cleanup_pending()
        return result
    state = read_json(STATE_FILE, {})
    return {"ok": True, "step": state.get("step", "phone")}


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("request must be an object")
        result = asyncio.run(run(payload))
        reply(bool(result.pop("ok", False)), **result)
    except Exception as exc:  # Keep web output concise and secret-free.
        reply(False, error=friendly_error(exc))


if __name__ == "__main__":
    main()
