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


def test_premiumplugx_playlist_entry_parser() -> None:
    playlist = """#EXTM3U
#EXTINF:-1 tvg-id="ten3-hd.sonyliv" tvg-name="Sony Ten 3 HD",Sony Ten 3 HD
#EXTVLCOPT:http-user-agent=UA
#EXTVLCOPT:http-referrer=https://www.sonyliv.com/
#EXTVLCOPT:http-cookie=hdnea=token
#EXTHTTP:{"Origin":"https://www.sonyliv.com","Referrer":"https://www.sonyliv.com/"}
https://example.com/master.m3u8?hdnea=token
"""
    entry = Downloader._find_m3u_entry(playlist, "ten3-hd.sonyliv")
    assert entry is not None
    assert entry["name"] == "Sony Ten 3 HD"
    assert entry["url"] == "https://example.com/master.m3u8?hdnea=token"
    headers = Downloader._normalise_stream_headers(entry["headers"])
    assert headers["User-Agent"] == "UA"
    assert headers["Referer"] == "https://www.sonyliv.com/"
    assert headers["Cookie"] == "hdnea=token"
    assert headers["Origin"] == "https://www.sonyliv.com"
