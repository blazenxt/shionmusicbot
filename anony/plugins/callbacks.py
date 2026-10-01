"""Inline button callbacks — playback controls, settings, navigation."""

from __future__ import annotations

import logging

from pyrogram import filters

from anony import bot, call, db, lang
from anony.helpers import fmt_duration, queue
from anony.helpers._admins import is_admin
from anony.helpers._inline import help_buttons, settings_buttons, stream_controls
from anony.helpers._player import advance, stop_and_clear
from anony.plugins.queue import build_queue_text

log = logging.getLogger(__name__)


async def _privileged(cq, chat_id: int) -> bool:
    """Sudo / chat-admin / auth-user check for a callback sender."""
    user = cq.from_user
    if user is None:
        return False
    if await db.is_sudo(user.id):
        return True
    if await is_admin(chat_id, user.id):
        return True
    return await db.is_auth(chat_id, user.id)


async def _cb_chat_id(cq) -> int:
    message = cq.message
    chat = getattr(message, "chat", None)
    return chat.id if chat is not None else (cq.message.chat.id if message else 0)


@bot.on_callback_query()
async def route_callbacks(client, cq):
    data = cq.data or ""
    parts = data.split("|")
    kind = parts[0] if parts else ""

    try:
        if kind == "ctr" and len(parts) >= 3:
            await _control(cq, parts[1], int(parts[2]))
        elif kind == "set" and len(parts) >= 2:
            await _setting(cq, parts[1], parts[2] if len(parts) > 2 else "")
        elif kind == "nav" and len(parts) >= 2:
            await _navigate(cq, parts[1])
        elif kind == "queue" and len(parts) >= 2:
            await _queue_page(cq, parts[1])
        else:
            await cq.answer()
    except Exception as exc:  # noqa: BLE001 - callbacks must never crash the loop
        log.exception("callback %r failed", data)
        try:
            await cq.answer(f"⚠️ {exc}"[:190], show_alert=True)
        except Exception:  # noqa: BLE001
            pass


# ── playback controls ──────────────────────────────────────────────────
async def _control(cq, action: str, chat_id: int):
    if action in ("pause", "resume", "skip", "stop", "loop", "clear") and not await _privileged(cq, chat_id):
        return await cq.answer(await lang.t(chat_id, "admin_only"), show_alert=True)

    if action == "pause":
        try:
            await call.pause(chat_id)
            return await cq.answer("⏸ Paused")
        except Exception:  # noqa: BLE001
            return await cq.answer(await lang.t(chat_id, "nothing_playing"))

    if action == "resume":
        try:
            await call.resume(chat_id)
            return await cq.answer("▶️ Resumed")
        except Exception:  # noqa: BLE001
            return await cq.answer(await lang.t(chat_id, "nothing_playing"))

    if action == "skip":
        current = queue.getnow(chat_id)
        await advance(chat_id, ignore_loop=True)
        try:
            await cq.message.edit_text(
                await lang.t(chat_id, "skipped", title=current.title if current else "track")
            )
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer("⏭ Skipped")

    if action == "stop":
        await stop_and_clear(chat_id)
        try:
            await cq.message.edit_text(await lang.t(chat_id, "stopped"))
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer("⏹ Stopped")

    if action == "loop":
        current = await db.get_loop(chat_id)
        new = 0 if current > 0 else 5
        await db.set_loop(chat_id, new)
        if new == 0:
            return await cq.answer(await lang.t(chat_id, "loop_off"))
        return await cq.answer(await lang.t(chat_id, "loop_set", n=new))

    if action == "queue":
        try:
            await cq.message.edit_text(await build_queue_text(chat_id))
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer("📋 Queue")

    if action == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer("✖ Closed")

    await cq.answer()


# ── settings ───────────────────────────────────────────────────────────
async def _setting(cq, what: str, value: str):
    chat_id = await _cb_chat_id(cq)
    user = cq.from_user

    # settings are for group admins (or private chat with the user)
    if chat_id and user and chat_id > 0:
        allowed = user.id == chat_id
    else:
        allowed = await _privileged(cq, chat_id)
    if not allowed:
        return await cq.answer(await lang.t(chat_id, "admin_only"), show_alert=True)

    if what == "lang" and value in lang.codes():
        await db.set_lang(chat_id, value)
        try:
            await cq.message.edit_text(
                await lang.t(chat_id, "settings_text"),
                reply_markup=settings_buttons(
                    value, await db.get_cmd_delete(chat_id)
                ),
            )
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer(
            await lang.t(chat_id, "settings_lang_set", lang=value.upper())
        )

    if what == "cdelete":
        new_state = not await db.get_cmd_delete(chat_id)
        await db.set_cmd_delete(chat_id, new_state)
        key = "settings_cdelete_on" if new_state else "settings_cdelete_off"
        try:
            await cq.message.edit_text(
                await lang.t(chat_id, "settings_text"),
                reply_markup=settings_buttons(
                    await db.get_lang(chat_id), new_state
                ),
            )
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer(await lang.t(chat_id, key))

    await cq.answer()


# ── navigation ─────────────────────────────────────────────────────────
async def _navigate(cq, where: str):
    chat_id = await _cb_chat_id(cq)

    if where == "help":
        try:
            await cq.message.edit_text(
                await lang.t(chat_id, "help_text"), reply_markup=help_buttons()
            )
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer()

    if where == "settings":
        code = await db.get_lang(chat_id)
        cdelete = await db.get_cmd_delete(chat_id)
        try:
            await cq.message.edit_text(
                await lang.t(chat_id, "settings_text"),
                reply_markup=settings_buttons(code, cdelete),
            )
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer()

    if where == "stats":
        from anony.plugins.stats import build_stats_text

        try:
            await cq.message.edit_text(await build_stats_text(chat_id))
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer()

    if where == "close":
        try:
            await cq.message.delete()
        except Exception:  # noqa: BLE001
            pass
        return await cq.answer("✖ Closed")

    await cq.answer()


# ── queue pagination ───────────────────────────────────────────────────
async def _queue_page(cq, page_raw: str):
    chat_id = await _cb_chat_id(cq)
    if page_raw == "noop":
        return await cq.answer()
    try:
        page = int(page_raw)
    except ValueError:
        page = 1
    try:
        await cq.message.edit_text(await build_queue_text(chat_id, page))
    except Exception:  # noqa: BLE001
        pass
    await cq.answer()
