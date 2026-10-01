"""Queue manager tests."""

from anony.helpers._dataclass import Media, Track
from anony.helpers._queue import Queue


def make_track(title="song", chat_id=-1001, video=False):
    return Track(
        media=Media(video_id="abc12345678", title=title, duration=120, duration_text="2:00"),
        chat_id=chat_id,
        requester_id=7,
        requester_name="Tester",
        is_video=video,
    )


def test_put_and_pop():
    q = Queue()
    assert q.put(-1001, make_track("a")) == 1
    assert q.put(-1001, make_track("b")) == 2
    assert q.size(-1001) == 2
    first = q.pop(-1001)
    assert first.title == "a"
    assert q.size(-1001) == 1


def test_now_slot():
    q = Queue()
    track = make_track("current")
    q.setnow(-1001, track)
    assert q.getnow(-1001).title == "current"
    q.setnow(-1001, None)
    assert q.getnow(-1001) is None


def test_remove_by_position():
    q = Queue()
    q.put(-1001, make_track("one"))
    q.put(-1001, make_track("two"))
    q.put(-1001, make_track("three"))
    removed = q.remove(-1001, 2)
    assert removed.title == "two"
    assert [t.title for t in q.get(-1001)] == ["one", "three"]
    assert q.remove(-1001, 99) is None


def test_force_add():
    q = Queue()
    q.put(-1001, make_track("later"))
    q.force_add(-1001, make_track("next"))
    assert q.get(-1001)[0].title == "next"


def test_clear_and_clear_all():
    q = Queue()
    q.put(-1001, make_track("x"))
    q.setnow(-1001, make_track("y"))
    assert q.clear(-1001) == 1
    assert q.getnow(-1001) is not None  # playing track survives /queue clear
    q.clear_all(-1001)
    assert q.getnow(-1001) is None


def test_replace():
    q = Queue()
    q.put(-1001, make_track("a"))
    q.replace(-1001, [make_track("b"), make_track("c")])
    assert [t.title for t in q.get(-1001)] == ["b", "c"]


def test_isolation_between_chats():
    q = Queue()
    q.put(-1001, make_track("mine"))
    q.put(-1002, make_track("theirs"))
    assert q.size(-1001) == 1
    assert q.size(-1002) == 1


def test_track_helpers():
    track = make_track("v", video=True)
    assert track.media.link == "https://youtu.be/abc12345678"
    assert "v" in track.summary()
    assert "🎬" in track.summary()
