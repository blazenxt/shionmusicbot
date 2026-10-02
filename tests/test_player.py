"""Queue-engine (player) logic tests with fakes."""

import time

import pytest

import anony
from anony.helpers import Media, Track
from anony.helpers._player import _cancel_idle, advance, on_stream_end
from anony.helpers._queue import queue
from anony.core.calls import TgCall


class FakeDB:
    def __init__(self):
        self.loops = {}

    async def get_loop(self, chat_id):
        return self.loops.get(chat_id, 0)

    async def set_loop(self, chat_id, count):
        self.loops[chat_id] = count

    async def incr_counter(self, name, by=1):
        return 0


class FakeCall:
    def __init__(self):
        self.played = []
        self.stopped = []

    async def play(self, chat_id, url, video=False, seek=0):
        self.played.append((chat_id, url, video, seek))

    async def stop(self, chat_id):
        self.stopped.append(chat_id)


class FakeBot:
    async def send_message(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_active_chats_uses_pytgcalls_async_property():
    class FakePyTgCalls:
        @property
        async def calls(self):
            return {-1001: object(), -1002: object()}

    manager = TgCall.__new__(TgCall)
    manager.app = FakePyTgCalls()
    assert await manager.active_chats() == [-1001, -1002]

    async def send_photo(self, *args, **kwargs):
        return None


class FakeLang:
    async def t(self, chat_id, key, **ctx):
        return key


class FakeYouTube:
    async def refresh_stream(self, video_id):
        # only the stream URL is refreshed; title/duration stay untouched
        return {"stream_url": f"http://mock/{video_id}"}

    async def session(self):
        raise RuntimeError("no session in tests")


@pytest.fixture()
def patched(monkeypatch):
    fake_db, fake_call = FakeDB(), FakeCall()
    monkeypatch.setattr(anony, "db", fake_db)
    monkeypatch.setattr(anony, "call", fake_call)
    monkeypatch.setattr(anony, "bot", FakeBot())
    monkeypatch.setattr(anony, "lang", FakeLang())
    from anony.helpers import _player

    monkeypatch.setattr(_player, "youtube", FakeYouTube())
    yield fake_db, fake_call, _player


def make_track(title, video=False):
    return Track(
        media=Media(video_id="vid" + title, title=title, duration=100, duration_text="1:40", stream_url="http://mock/vid" + title),
        chat_id=-1001,
        requester_id=1,
        requester_name="t",
        is_video=video,
    )


@pytest.fixture(autouse=True)
def clean_queue():
    from anony.helpers import _player

    queue.clear_all(-1001)
    _player._started_at.clear()
    _player._recovery_attempts.clear()
    _player._advancing.clear()
    yield
    queue.clear_all(-1001)
    _player._started_at.clear()
    _player._recovery_attempts.clear()
    _player._advancing.clear()


async def test_advance_replays_when_looping(patched):
    fake_db, fake_call, _player = patched
    current = make_track("current")
    queue.setnow(-1001, current)
    queue.put(-1001, make_track("next"))
    fake_db.loops[-1001] = 2

    await advance(-1001)

    assert len(fake_call.played) == 1
    assert queue.getnow(-1001).title == "current"
    assert queue.size(-1001) == 1  # next stays queued
    assert fake_db.loops[-1001] == 1  # decremented
    _cancel_idle(-1001)


async def test_advance_pops_queue_when_no_loop(patched):
    fake_db, fake_call, _player = patched
    queue.setnow(-1001, make_track("current"))
    queue.put(-1001, make_track("next1"))
    queue.put(-1001, make_track("next2"))

    await advance(-1001)

    assert len(fake_call.played) == 1
    assert fake_call.played[0][0] == -1001
    assert queue.getnow(-1001).title == "next1"
    assert queue.size(-1001) == 1
    _cancel_idle(-1001)


async def test_advance_skips_failing_tracks(patched):
    fake_db, fake_call, _player = patched
    queue.put(-1001, make_track("good"))
    queue.setnow(-1001, None)
    _player._advancing[-1001] = 0  # reset debounce

    await advance(-1001)

    assert queue.getnow(-1001) is not None
    assert queue.size(-1001) == 0
    _cancel_idle(-1001)


async def test_advance_empty_keeps_call_when_auto_end_disabled(patched):
    fake_db, fake_call, _player = patched
    queue.setnow(-1001, None)
    _player._advancing[-1001] = 0

    await advance(-1001)

    assert queue.getnow(-1001) is None
    # AUTO_END is false in the test/default config: the assistant remains in
    # the voice chat and no hidden two-minute leave task is created.
    assert -1001 not in _player._idle_tasks
    assert fake_call.stopped == []
    assert fake_db.loops.get(-1001, 0) == 0
    _cancel_idle(-1001)


async def test_stream_end_debounce(patched):
    fake_db, fake_call, _player = patched
    queue.setnow(-1001, make_track("current"))
    fake_db.loops[-1001] = 1

    await on_stream_end(-1001)   # audio end → advance
    await on_stream_end(-1001)   # video end → debounced

    assert len(fake_call.played) == 1
    _cancel_idle(-1001)


async def test_premature_stream_end_resumes_instead_of_dropping_call(patched):
    fake_db, fake_call, _player = patched
    current = make_track("current")
    queue.setnow(-1001, current)
    _player._started_at[-1001] = time.monotonic() - 30

    await on_stream_end(-1001)

    assert len(fake_call.played) == 1
    assert fake_call.played[0][3] >= 27
    assert queue.getnow(-1001) is current
    assert _player._recovery_attempts[-1001] == 1
    _cancel_idle(-1001)
