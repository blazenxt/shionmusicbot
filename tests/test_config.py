"""Configuration loader tests."""

from config import Config, config, validate


def test_config_loaded():
    assert config.API_ID > 0
    assert len(config.API_HASH) >= 32
    assert ":" in config.BOT_TOKEN
    assert config.BOT_USERNAME == "ShionMusicBot"
    assert config.OWNER_ID == 7330774855
    assert config.LANG_CODE in ("en", "hi")


def test_validate_passes():
    # conftest (or .env) always provides a full configuration
    assert validate() == []


def test_duration_limit_conversion():
    assert config.duration_limit_secs == config.DURATION_LIMIT * 60


def test_assistant_session_fallback():
    # SESSION_STRING wins, SESSION1 is the fallback
    cfg = Config(SESSION1="AAA", SESSION_STRING="BBB")
    assert cfg.assistant_session == "BBB"
    cfg = Config(SESSION1="AAA")
    assert cfg.assistant_session == "AAA"


def test_yt_api_base_normalised(monkeypatch):
    monkeypatch.setenv("YT_API_BASE", "http://Testweb3.cstsc.in/yt")
    from config import _build

    assert _build().YT_API_BASE == "http://Testweb3.cstsc.in/yt/"


def test_deep_link():
    assert config.deep_link().startswith("https://t.me/ShionMusicBot?")
