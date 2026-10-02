"""Live page/HLS resolver and Telegram 9.4 style tests."""

import urllib.parse

import pytest

from anony.core.live import LiveResolveError, _parse_m3u, _validate_public_url
from anony.core.live_proxy import LiveHLSProxy, build_live_raw_stream
from anony.helpers._inline import DANGER, PRIMARY, SUCCESS, stream_controls


PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="ten3-hd.sonyliv" tvg-name="Sony Ten 3 HD",Sony Ten 3 HD
#EXTVLCOPT:http-user-agent=Mozilla/5.0 Test
#EXTVLCOPT:http-referrer=https://www.sonyliv.com/
#EXTVLCOPT:http-cookie=hdnea=token
https://cdn.example.com/live/ten3/master.m3u8?hdnea=token
"""


def test_parse_m3u_channel_and_headers():
    source = _parse_m3u(PLAYLIST, "ten3-hd.sonyliv")
    assert source is not None
    assert source.title == "Sony Ten 3 HD"
    assert source.url.endswith("master.m3u8?hdnea=token")
    assert source.headers["User-Agent"] == "Mozilla/5.0 Test"
    assert source.headers["Referer"] == "https://www.sonyliv.com/"
    assert source.headers["Cookie"] == "hdnea=token"


def test_parse_m3u_rejects_other_channel():
    assert _parse_m3u(PLAYLIST, "different.sonyliv") is None


@pytest.mark.asyncio
async def test_live_url_ssrf_guard_rejects_loopback():
    with pytest.raises(LiveResolveError):
        await _validate_public_url("http://127.0.0.1/private.m3u8")


def test_live_raw_stream_removes_vod_reconnect_flags():
    stream = build_live_raw_stream("http://127.0.0.1:12345/live.m3u8", True)
    assert "-reconnect" not in stream.microphone.path
    assert "-reconnect" not in stream.camera.path
    assert "-f s16le" in stream.microphone.path
    assert "-f rawvideo" in stream.camera.path


def test_hls_proxy_rejects_unsafe_proxy_endpoints():
    assert LiveHLSProxy._is_public_proxy("http://8.8.8.8:8080") is True
    assert LiveHLSProxy._is_public_proxy("http://127.0.0.1:8080") is False
    assert LiveHLSProxy._is_public_proxy("http://10.0.0.2:3128") is False
    assert LiveHLSProxy._is_public_proxy("https://8.8.8.8:8080") is False


def test_hls_proxy_rewrites_relative_segments_and_uri_attributes():
    proxy = LiveHLSProxy()
    proxy._port = 12345
    rewritten = proxy._rewrite_playlist(
        '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="keys/key.bin"\nvideo/segment.ts\n',
        "https://cdn.example.com/live/master.m3u8",
        "test-token",
    )
    relay_urls = []
    for value in rewritten.replace('URI="', "\n").replace('"', "\n").splitlines():
        if value.startswith("http://127.0.0.1:12345/test-token/"):
            relay_urls.append(value)
    decoded = {
        proxy._decode(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
        for url in relay_urls
    }
    assert decoded == {
        "https://cdn.example.com/live/keys/key.bin",
        "https://cdn.example.com/live/video/segment.ts",
    }


def test_telegram_94_semantic_button_styles():
    markup = stream_controls(-1001)
    assert markup.inline_keyboard[0][0].style.bg_primary is True
    assert markup.inline_keyboard[0][2].style.bg_danger is True
    assert markup.inline_keyboard[1][0].style.bg_success is True
    assert PRIMARY.bg_primary and SUCCESS.bg_success and DANGER.bg_danger
