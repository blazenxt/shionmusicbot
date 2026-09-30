from shionmusicbot.downloader import Downloader


def test_extract_youtube_id_variants() -> None:
    assert Downloader._extract_youtube_id("60ItHLz5WEA") == "60ItHLz5WEA"
    assert Downloader._extract_youtube_id("https://youtu.be/60ItHLz5WEA") == "60ItHLz5WEA"
    assert (
        Downloader._extract_youtube_id("https://www.youtube.com/watch?v=60ItHLz5WEA")
        == "60ItHLz5WEA"
    )
    assert (
        Downloader._extract_youtube_id("https://youtube.com/shorts/60ItHLz5WEA?si=x")
        == "60ItHLz5WEA"
    )
    assert Downloader._extract_youtube_id("faded alan walker") is None


def test_payload_source_prefers_recovery_stream() -> None:
    payload = {
        "qualities": [{"url": "manifest.php?id=1"}],
        "recovery_stream": {"url": "stream.php?t=abc&s=def"},
    }
    assert Downloader._payload_source(payload) == "stream.php?t=abc&s=def"


def test_payload_source_accepts_qualities_fallback() -> None:
    payload = {
        "qualities": [
            {"type": "dash", "url": "manifest.php?id=1"},
            {"type": "progressive", "url": "stream.php?t=abc"},
        ]
    }
    assert Downloader._payload_source(payload) == "stream.php?t=abc"
