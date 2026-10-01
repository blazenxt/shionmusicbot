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


def cleanup_pending() -> None:
    STATE_FILE.unlink(missing_ok=True)
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
        return await send_code(payload, env)
    if action == "resend":
        return await resend_code(env)
    if action == "verify":
        return await verify_code(payload, env)
    if action == "password":
        return await verify_password(payload, env)
    if action == "reset":
        cleanup_pending()
        return {"ok": True, "step": "phone"}
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
        name = type(exc).__name__
        messages = {
            "PhoneNumberInvalid": "The phone number is invalid.",
            "PhoneNumberBanned": "Telegram has banned this phone number.",
            "PhoneCodeInvalid": "The Telegram login code is incorrect.",
            "PhoneCodeExpired": "The Telegram login code expired. Request a new code.",
            "PasswordHashInvalid": "The two-step verification password is incorrect.",
            "FloodWait": "Telegram rate-limited this login. Please wait and try again.",
        }
        reply(False, error=messages.get(name, f"Telegram login failed ({name})."))


if __name__ == "__main__":
    main()
