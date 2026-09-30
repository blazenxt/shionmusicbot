#!/usr/bin/env python3
"""Generate a Pyrogram session string for the assistant user account.

Run this locally or on the server:
    python scripts/generate_session.py

Telegram will send an OTP to the assistant number. Paste the printed SESSION_STRING
into your .env file. Never commit SESSION_STRING to git.
"""

from __future__ import annotations

import asyncio
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from pyrogram import Client  # noqa: E402


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}. Put it in .env or export it first.")
    return value


async def main() -> None:
    api_id = int(required("API_ID"))
    api_hash = required("API_HASH")
    phone = (
        os.getenv("ASSISTANT_PHONE") or input("Assistant phone number with country code: ").strip()
    )

    async with Client(
        "shion_session_generator",
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone,
        in_memory=True,
    ) as app:
        session = await app.export_session_string()

    print('\nSESSION_STRING="' + session + '"\n')
    print("Copy the line above into .env. Keep it private.")


if __name__ == "__main__":
    asyncio.run(main())
