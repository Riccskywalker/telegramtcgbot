"""Test dello store dei gruppi e della logica di membership (niente rete)."""

from rarebit_bot.groups import (
    Group,
    GroupStore,
    is_trackable_chat,
    membership_is_present,
)


def test_present_statuses():
    assert membership_is_present("member", None)
    assert membership_is_present("administrator", None)
    assert membership_is_present("creator", None)
    assert membership_is_present("restricted", True)
    assert not membership_is_present("restricted", False)
    assert not membership_is_present("left", None)
    assert not membership_is_present("kicked", None)
    assert not membership_is_present(None, None)


def test_trackable_only_groups_and_channels():
    assert is_trackable_chat("group")
    assert is_trackable_chat("supergroup")
    assert is_trackable_chat("channel")
    assert not is_trackable_chat("private")
    assert not is_trackable_chat(None)


def test_upsert_remove_and_owner_filter(tmp_path):
    store = GroupStore(str(tmp_path / "groups.json"))
    store.upsert(Group(chat_id=-100, type="supergroup", title="A", added_by=7))
    store.upsert(Group(chat_id=-200, type="group", title="B", added_by=9))
    assert len(store) == 2
    assert {g.chat_id for g in store.for_owner(7)} == {-100}
    assert store.for_owner(123) == []
    store.remove(-100)
    assert len(store) == 1
    store.remove(-999)  # rimuovere un id assente è un no-op
    assert len(store) == 1


def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "groups.json")
    s1 = GroupStore(path)
    s1.upsert(
        Group(chat_id=-100, type="channel", title="RareBit", added_by=7, is_admin=True)
    )
    # una nuova istanza ricarica da disco
    s2 = GroupStore(path)
    assert len(s2) == 1
    g = s2.all()[0]
    assert g.chat_id == -100
    assert g.type == "channel"
    assert g.is_admin is True
    assert g.added_by == 7


def test_upsert_overwrites_same_chat(tmp_path):
    store = GroupStore(str(tmp_path / "groups.json"))
    store.upsert(Group(chat_id=-100, type="group", title="old", added_by=7))
    store.upsert(
        Group(chat_id=-100, type="supergroup", title="new", added_by=7, is_admin=True)
    )
    assert len(store) == 1
    only = store.all()[0]
    assert only.title == "new"
    assert only.is_admin is True


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "groups.json"
    path.write_text("{ not valid json", encoding="utf-8")
    store = GroupStore(str(path))
    assert len(store) == 0
