from shionmusicbot.utils import format_duration, is_url, parse_duration, truncate


def test_parse_duration_seconds() -> None:
    assert parse_duration("90") == 90


def test_parse_duration_clock() -> None:
    assert parse_duration("1:30") == 90
    assert parse_duration("1:02:03") == 3723


def test_parse_duration_words() -> None:
    assert parse_duration("1h 2m 3s") == 3723
    assert parse_duration("2m10s") == 130


def test_format_duration() -> None:
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"
    assert format_duration(None) == "Live"


def test_is_url() -> None:
    assert is_url("https://example.com/a.mp3")
    assert not is_url("not a url")


def test_truncate() -> None:
    assert truncate("hello", 10) == "hello"
    assert truncate("hello world", 6) == "hello…"
