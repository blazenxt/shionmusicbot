"""Utility + dataclass tests."""

from anony.helpers import extract_query, fmt_duration, get_urls, human_count, truncate
from anony.helpers._utilities import parse_duration
from anony.core.youtube import duration_text, seconds_from_text, video_id_from_url


class FakeUser:
    def __init__(self, first_name="Tester"):
        self.first_name = first_name


class FakeMessage:
    def __init__(self, text=None, caption=None, reply_text=None):
        self.text = text
        self.caption = caption
        if reply_text is not None:
            class _Reply:
                pass

            self.reply_to_message = _Reply()
            self.reply_to_message.text = reply_text
            self.reply_to_message.caption = None
        else:
            self.reply_to_message = None


def test_fmt_duration():
    assert fmt_duration(0) == "0:00"
    assert fmt_duration(65) == "1:05"
    assert fmt_duration(3671) == "1:01:11"
    assert fmt_duration(None) == "0:00"


def test_parse_duration():
    assert parse_duration("1:30") == 90
    assert parse_duration("1:00:00") == 3600
    assert parse_duration("45") == 45
    assert parse_duration("") == 0
    assert parse_duration("xx:yy") == 0


def test_duration_helpers_module():
    assert duration_text(213) == "3:33"
    assert seconds_from_text("3:33") == 213


def test_get_urls():
    text = "check https://youtu.be/60ItHLz5WEA and http://example.com/a?b=1"
    urls = get_urls(text)
    assert len(urls) == 2
    assert urls[0].endswith("60ItHLz5WEA")
    assert get_urls(None) == []
    assert get_urls("no links") == []


def test_video_id_from_url():
    assert video_id_from_url("https://www.youtube.com/watch?v=60ItHLz5WEA") == "60ItHLz5WEA"
    assert video_id_from_url("https://youtu.be/60ItHLz5WEA?t=10") == "60ItHLz5WEA"
    assert video_id_from_url("https://www.youtube.com/shorts/60ItHLz5WEA") == "60ItHLz5WEA"
    assert video_id_from_url("https://example.com/nope") is None
    assert video_id_from_url("") is None


def test_extract_query():
    msg = FakeMessage(text="/play faded alan walker")
    assert extract_query(msg) == "faded alan walker"

    msg = FakeMessage(text="/play@ShionMusicBot believer")
    assert extract_query(msg) == "believer"

    msg = FakeMessage(text="/play", reply_text="https://youtu.be/60ItHLz5WEA")
    assert extract_query(msg) == "https://youtu.be/60ItHLz5WEA"

    msg = FakeMessage(text="/play")
    assert extract_query(msg) is None

    msg = FakeMessage(text=None, caption="/play from caption song")
    assert extract_query(msg) == "from caption song"


def test_human_count():
    assert human_count(999) == "999"
    assert human_count(1200) == "1.2K"
    assert human_count(2500000) == "2.5M"
    assert human_count("nope") == "nope"


def test_truncate():
    assert truncate("short") == "short"
    assert len(truncate("x" * 100, 20)) == 19 + 1  # 19 chars + ellipsis
    assert truncate("x" * 100, 20).endswith("…")
