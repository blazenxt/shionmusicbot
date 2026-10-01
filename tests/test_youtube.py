"""Testweb3 engine tests against a local aiohttp mock server."""

import socket

import pytest
from aiohttp import web

from anony.core.youtube import YouTubeEngine

SEARCH_PAYLOAD = {
    "ok": True,
    "data": {
        "videos": [
            {
                "id": "60ItHLz5WEA",
                "title": "Alan Walker - Faded",
                "thumbnail": "http://127.0.0.1/thumb.jpg",
                "channel": "Alan Walker",
                "duration": 213,
                "duration_text": "3:33",
                "views": 1_000_000,
                "is_live": False,
            },
            {
                "id": "LIVEVID1111",
                "title": "Live Concert",
                "duration": 0,
                "is_live": True,
            },
        ]
    },
}

VIDEO_PAYLOAD = {
    "ok": True,
    "data": {
        "id": "60ItHLz5WEA",
        "title": "Alan Walker - Faded",
        "duration": 213,
        "thumbnail": "http://127.0.0.1/thumb.jpg",
        "channel": "Alan Walker",
        "views": 1_000_000,
        "is_live": False,
        "recovery_stream": {
            "label": "Compatibility",
            "height": 360,
            "type": "progressive",
            "url": "stream.php?t=abc123",
        },
    },
}


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture()
async def engine():
    async def handler(request):
        action = request.query.get("action")
        if action == "search":
            if not request.query.get("q"):
                return web.json_response({"ok": False, "error": "empty query"}, status=400)
            return web.json_response(SEARCH_PAYLOAD)
        if action == "video":
            return web.json_response(VIDEO_PAYLOAD)
        return web.json_response({"ok": False, "error": "bad action"}, status=400)

    app = web.Application()
    app.router.add_get("/yt/api.php", handler)

    port = free_port()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    eng = YouTubeEngine(base_url=f"http://127.0.0.1:{port}/yt/")
    try:
        yield eng
    finally:
        await eng.close()
        await runner.cleanup()


async def test_search_normalisation(engine):
    results = await engine.search("faded")
    assert len(results) == 1  # live stream filtered out
    first = results[0]
    assert first["id"] == "60ItHLz5WEA"
    assert first["title"] == "Alan Walker - Faded"
    assert first["duration"] == 213
    assert first["duration_text"] == "3:33"
    assert first["is_live"] is False


async def test_video_resolves_absolute_stream(engine):
    info = await engine.video("60ItHLz5WEA")
    assert info is not None
    assert info["title"] == "Alan Walker - Faded"
    # relative recovery_stream URL must resolve against the engine base
    assert info["stream_url"].startswith("http://127.0.0.1:")
    assert info["stream_url"].endswith("/yt/stream.php?t=abc123")


async def test_video_cache(engine):
    first = await engine.video("60ItHLz5WEA")
    second = await engine.video("60ItHLz5WEA")  # served from cache
    assert first == second


async def test_refresh_bypasses_cache(engine):
    await engine.video("60ItHLz5WEA")
    refreshed = await engine.refresh_stream("60ItHLz5WEA")
    assert refreshed is not None
    assert refreshed["stream_url"].endswith("stream.php?t=abc123")


async def test_search_limit(engine):
    results = await engine.search("anything", limit=1)
    assert len(results) <= 1


async def test_bad_engine_errors_are_soft(engine):
    results = await engine.search("")  # mock rejects empty queries with HTTP 400
    assert results == []
    missing = await engine.video("zzzzzzzzzzz")
    # the mock answers any id; verify shape only
    assert missing is None or isinstance(missing, dict)


async def test_unreachable_engine():
    eng = YouTubeEngine(base_url="http://127.0.0.1:1/yt/", timeout=3)
    assert await eng.search("anything") == []
    assert await eng.video("60ItHLz5WEA") is None
    await eng.close()
