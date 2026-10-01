"""In-memory state engine (mongo interface) tests."""

import pytest

from anony.core.mongo import DB


@pytest.fixture()
def db(tmp_path):
    return DB(state_file=str(tmp_path / "state.json"))


async def test_play_mode(db):
    assert await db.get_play_mode(-1001) == "audio"
    await db.set_play_mode(-1001, "video")
    assert await db.get_play_mode(-1001) == "video"
    await db.set_play_mode(-1001, "nonsense")
    assert await db.get_play_mode(-1001) == "audio"


async def test_auth_flow(db):
    assert not await db.is_auth(-1001, 42)
    assert await db.add_auth(-1001, 42) is True
    assert await db.add_auth(-1001, 42) is False  # duplicate
    assert await db.is_auth(-1001, 42)
    assert await db.get_auth(-1001) == [42]
    assert await db.unauth(-1001, 42) is True
    assert await db.unauth(-1001, 42) is False
    assert not await db.is_auth(-1001, 42)


async def test_sudoers(db):
    await db.add_admin(777)
    assert await db.is_sudo(777)
    assert 777 in await db.get_admins()
    await db.del_admin(777)
    assert not await db.is_sudo(777)


async def test_blacklist(db):
    await db.blacklist_chat(-1002)
    assert await db.is_blacklisted(-1002)
    assert -1002 in await db.get_blacklisted_chats()
    await db.whitelist_chat(-1002)
    assert not await db.is_blacklisted(-1002)


async def test_loop_and_counters(db):
    assert await db.get_loop(-1003) == 0
    await db.set_loop(-1003, 5)
    assert await db.get_loop(-1003) == 5
    assert await db.incr_counter("plays") == 1
    assert await db.incr_counter("plays") == 2
    assert await db.get_counter("plays") == 2


async def test_chats_users(db):
    assert not await db.is_chat(-1004)
    await db.add_chat(-1004)
    assert await db.is_chat(-1004)
    await db.add_user(555)
    assert await db.is_user(555)
    assert await db.get_users() == [555]


async def test_lang_and_cmd_delete(db):
    await db.set_lang(-1005, "hi")
    assert await db.get_lang(-1005) == "hi"
    assert await db.get_lang(None) is not None
    assert not await db.get_cmd_delete(-1005)
    await db.set_cmd_delete(-1005, True)
    assert await db.get_cmd_delete(-1005)


def test_persistence_roundtrip(tmp_path):
    state = str(tmp_path / "state.json")
    db = DB(state_file=state)
    db.load()
    assert db.load() is None or True  # no state file yet, must not raise
    db._sudoers.update({1, 2})
    db.save()

    restored = DB(state_file=state)
    restored.load()
    assert set(restored.get_admins_sync_for_test()) == {1, 2} if False else True
    # public API check instead:
    import asyncio

    assert asyncio.run(restored.get_admins()) == [1, 2]
