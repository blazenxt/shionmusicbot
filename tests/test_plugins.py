"""Plugin package integrity tests."""

import importlib
import pkgutil

import anony
import anony.plugins

EXPECTED = {
    "start", "ping", "play", "pause", "resume", "stop", "skip", "seek",
    "queue", "loop", "callbacks", "auth", "sudoers", "blacklist",
    "broadcast", "stats", "misc", "lang", "id", "tools", "volume", "shuffle", "live",
}


def test_exactly_23_plugin_modules():
    found = {
        mod.name
        for mod in pkgutil.iter_modules(anony.plugins.__path__)
        if not mod.name.startswith("_")
    }
    assert found == EXPECTED
    assert len(found) == 23


def test_every_plugin_imports():
    for name in sorted(EXPECTED):
        importlib.import_module(f"anony.plugins.{name}")


def test_handlers_registered_on_bot():
    groups = anony.bot.dispatcher.groups
    total = sum(len(handlers) for handlers in groups.values())
    assert total >= 25, f"expected ≥25 handlers, got {total}"
    # command handlers must exist in group 0
    assert any(handlers for handlers in groups.get(0, []))


def test_private_fallback_does_not_shadow_commands():
    from anony.plugins.misc import GROUP_ONLY_COMMANDS, KNOWN_COMMANDS

    assert {"start", "help", "settings", "ping"}.issubset(KNOWN_COMMANDS)
    assert {"play", "vplay", "live", "vlive", "queue", "skip"}.issubset(GROUP_ONLY_COMMANDS)
    assert set(GROUP_ONLY_COMMANDS).issubset(KNOWN_COMMANDS)
    assert len(KNOWN_COMMANDS) == len(set(KNOWN_COMMANDS))


def test_callback_handler_registered():
    from pyrogram.handlers import CallbackQueryHandler

    groups = anony.bot.dispatcher.groups
    flat = [h for handlers in groups.values() for h in handlers]
    assert any(isinstance(h, CallbackQueryHandler) for h in flat)


def test_core_singletons():
    assert anony.bot is not None
    assert anony.userbot is not None
    assert anony.call is not None
    assert anony.db is not None
    assert anony.lang is not None
    assert anony.__version__ == "1.0.0"
    assert anony.BOOT_TIME > 0


def test_locale_files_complete():
    en = anony.lang.strings.get("en", {})
    hi = anony.lang.strings.get("hi", {})
    assert en and hi
    assert set(en) == set(hi), "en/hi key sets diverge"
    for key in (
        "start_private", "help_text", "now_playing", "added_queue", "queue_full",
        "assistant_missing", "stopped", "skipped", "seek_done", "loop_set",
        "auth_added", "sudo_added", "bl_added", "broadcast_done", "stats_text",
        "ping_text", "play_usage", "volume_set", "queue_shuffled",
    ):
        assert key in en, f"missing locale key: {key}"
