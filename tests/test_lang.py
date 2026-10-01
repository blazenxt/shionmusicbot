"""Translation service tests."""

from anony import db, lang
from anony.core.lang import Lang


def test_packs_loaded():
    codes = lang.codes()
    assert "en" in codes
    assert "hi" in codes


def test_english_direct():
    assert "Now playing" in lang.get("en", "now_playing")


def test_missing_key_falls_back_to_key():
    assert lang.get("en", "no_such_key_at_all") == "no_such_key_at_all"


def test_unknown_language_falls_back_to_english():
    assert lang.get("xx", "now_playing") == lang.get("en", "now_playing")


async def test_t_with_formatting():
    text = await lang.t(None, "added_queue", title="Believer", duration="3:07", user="zuc", position=2)
    assert "Believer" in text
    assert "3:07" in text
    assert "zuc" in text
    assert "#2" in text


async def test_per_chat_language():
    chat = -991234
    await db.set_lang(chat, "hi")
    hindi = await lang.t(chat, "paused")
    assert "रोक" in hindi
    await db.set_lang(chat, "en")
    english = await lang.t(chat, "paused")
    assert "paused" in english.lower()
    assert english != hindi


def test_translator_attribute_access():
    translator = lang  # language service itself
    assert translator.get("en", "paused")
    svc = Lang()
    # direct translator object usage
    from anony.core.lang import Translator

    t = Translator(svc, "en")
    assert "Now playing" in t.now_playing
    assert t.code == "en"
