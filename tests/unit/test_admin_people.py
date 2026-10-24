"""Admin dashboard: the Channels table names who is in each channel, not just how many."""
from types import SimpleNamespace

from app import lk


def test_channel_row_lists_people_by_name(admin_client, sample_room, monkeypatch):
    monkeypatch.setattr(lk, "list_rooms_participants", lambda: {sample_room: 2})
    monkeypatch.setattr(lk, "list_participants", lambda room: [
        SimpleNamespace(name="zed (Admin-US)", identity="12"), SimpleNamespace(name="", identity="34")])
    html = admin_client.get("/admin").get_data(as_text=True)
    assert '<ul class="who"><li>34</li><li>zed (Admin-US)</li></ul>' in html    # no name -> identity; sorted


def test_empty_channel_has_no_name_list(admin_client, sample_room, monkeypatch):
    monkeypatch.setattr(lk, "list_rooms_participants", lambda: {})
    called = []
    monkeypatch.setattr(lk, "list_participants", lambda room: called.append(room) or [])
    assert 'class="who"' not in admin_client.get("/admin").get_data(as_text=True)
    assert called == []                                           # no LiveKit call for an empty channel


def test_livekit_error_keeps_the_count(admin_client, sample_room, monkeypatch):
    monkeypatch.setattr(lk, "list_rooms_participants", lambda: {sample_room: 3})
    def boom(room):
        raise RuntimeError("livekit down")
    monkeypatch.setattr(lk, "list_participants", boom)
    r = admin_client.get("/admin")
    assert r.status_code == 200
    assert 'class="who"' not in r.get_data(as_text=True)
