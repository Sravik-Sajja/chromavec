"""
Tests for api.py

Spotify credentials are faked before import since api.py builds a module-level SpotifyOAuth client at import time
"""
import os

os.environ.setdefault("SPOTIFY_CLIENT_ID", "test-client-id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def client():
    return TestClient(api.app)


@pytest.fixture
def mock_sp():
    """Replaces the module-level `sp` client entirely for the duration
    of a test, since api.py talks to it as a plain module global."""
    with patch.object(api, "sp") as mock:
        yield mock


def _accessible_playlist(playlist_id="pl1", name="My Playlist", owner_id="user1", snapshot_id="snap1"):
    return {
        "id": playlist_id,
        "name": name,
        "owner": {"id": owner_id},
        "snapshot_id": snapshot_id,
    }


# ── /login ────────────────────────────────────────────────────────────────

def test_login_redirects_to_spotify_auth_url(client, mock_sp):
    mock_sp.auth_manager.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?x=1"

    resp = client.get("/login", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://accounts.spotify.com/authorize?x=1"


# ── /callback ─────────────────────────────────────────────────────────────

def test_callback_exchanges_code_and_redirects_home(client, mock_sp):
    resp = client.get("/callback?code=abc123", follow_redirects=False)

    mock_sp.auth_manager.get_access_token.assert_called_once_with("abc123")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/home"


def test_callback_requires_code_param(client, mock_sp):
    resp = client.get("/callback")
    assert resp.status_code == 422  # missing required query param


# ── collect_tracks (pure function, no HTTP layer needed) ───────────────────

def test_collect_tracks_extracts_expected_fields():
    fake_sp = MagicMock()
    fake_sp.playlist_items.return_value = {
        "items": [
            {"item": {
                "id": "t1", "name": "Song A", "duration_ms": 200000,
                "artists": [{"name": "Artist A"}],
                "album": {"name": "Album A"},
            }},
        ],
        "next": None,
    }

    track_ids, tracks = api.collect_tracks(fake_sp, "pl1")

    assert track_ids == ["t1"]
    assert tracks == [{
        "id": "t1", "name": "Song A", "artist": "Artist A",
        "album": "Album A", "duration_ms": 200000,
    }]


def test_collect_tracks_skips_items_with_no_track_or_no_id():
    fake_sp = MagicMock()
    fake_sp.playlist_items.return_value = {
        "items": [
            {"item": None},
            {"item": {"id": None, "name": "Ghost"}},
            {"item": {"id": "t2", "name": "Real Song", "artists": [{"name": "A"}], "album": {}}},
        ],
        "next": None,
    }

    track_ids, tracks = api.collect_tracks(fake_sp, "pl1")

    assert track_ids == ["t2"]


def test_collect_tracks_handles_missing_artists_gracefully():
    fake_sp = MagicMock()
    fake_sp.playlist_items.return_value = {
        "items": [
            {"item": {"id": "t1", "name": "Instrumental", "artists": [], "album": {}}},
        ],
        "next": None,
    }

    _, tracks = api.collect_tracks(fake_sp, "pl1")
    assert tracks[0]["artist"] == ""


def test_collect_tracks_paginates_through_next_page():
    fake_sp = MagicMock()
    page1 = {
        "items": [{"item": {"id": "t1", "name": "A", "artists": [{"name": "X"}], "album": {}}}],
        "next": "page2-token",
    }
    page2 = {
        "items": [{"item": {"id": "t2", "name": "B", "artists": [{"name": "Y"}], "album": {}}}],
        "next": None,
    }
    fake_sp.playlist_items.return_value = page1
    fake_sp.next.side_effect = [page2]

    track_ids, _ = api.collect_tracks(fake_sp, "pl1")

    assert track_ids == ["t1", "t2"]
    fake_sp.next.assert_called_once_with(page1)


# ── /playlists ────────────────────────────────────────────────────────────

def test_playlists_excludes_playlists_the_user_cant_access(client, mock_sp):
    mock_sp.current_user.return_value = {"id": "user1"}
    mock_sp.current_user_playlists.return_value = {
        "items": [_accessible_playlist(playlist_id="private", owner_id="someone_else")]
    }
    mock_sp.playlist_tracks.side_effect = Exception("403 forbidden")

    resp = client.get("/playlists")

    assert resp.json() == {"items": []}


def test_playlists_includes_playlists_user_owns(client, mock_sp):
    mock_sp.current_user.return_value = {"id": "user1"}
    mock_sp.current_user_playlists.return_value = {
        "items": [_accessible_playlist(owner_id="user1")]
    }

    with patch("api.snapshots") as mock_snapshots, \
         patch("api.collect_tracks", return_value=(["t1", "t2"], [])) as mock_collect, \
         patch("api.get_playlist_recommendations", return_value=[]), \
         patch("api.process_playlist_task") as mock_task:
        mock_snapshots.is_up_to_date.return_value = False
        mock_snapshots.is_processing.return_value = False
        mock_task.delay.return_value = MagicMock(id="job-abc")

        resp = client.get("/playlists")

    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == "pl1"
    assert body["items"][0]["job_id"] == "job-abc"
    mock_collect.assert_called_once()


def test_playlists_cache_hit_skips_celery_and_returns_result_inline(client, mock_sp):
    mock_sp.current_user.return_value = {"id": "user1"}
    mock_sp.current_user_playlists.return_value = {
        "items": [_accessible_playlist(owner_id="user1", snapshot_id="snap1")]
    }

    with patch("api.snapshots") as mock_snapshots, \
         patch("api.collect_tracks", return_value=(["t1", "t2"], [])), \
         patch("api.get_playlist_recommendations", return_value=[{"name": "Rec", "artist": "A", "score": 90.0}]), \
         patch("api.process_playlist_task") as mock_task:
        mock_snapshots.get_snapshot.return_value = {"total_tracks": 2, "total_ingested": 2}
        mock_snapshots.is_up_to_date.return_value = True

        resp = client.get("/playlists")

    item = resp.json()["items"][0]
    assert item["job_id"] is None
    assert item["result"]["total_ingested"] == 2
    assert item["result"]["track_ids"] == ["t1", "t2"]
    assert item["result"]["recommendations"][0]["name"] == "Rec"
    mock_task.delay.assert_not_called()


def test_playlists_already_processing_reuses_existing_job_without_reenqueue(client, mock_sp):
    mock_sp.current_user.return_value = {"id": "user1"}
    mock_sp.current_user_playlists.return_value = {
        "items": [_accessible_playlist(owner_id="user1", snapshot_id="snap1")]
    }

    with patch("api.snapshots") as mock_snapshots, \
         patch("api.collect_tracks") as mock_collect, \
         patch("api.process_playlist_task") as mock_task:
        mock_snapshots.is_up_to_date.return_value = False
        mock_snapshots.is_processing.return_value = True
        mock_snapshots.get_snapshot.return_value = {
            "job_id": "existing-job-id", "total_tracks": 10,
        }

        resp = client.get("/playlists")

    item = resp.json()["items"][0]
    assert item["job_id"] == "existing-job-id"
    assert item["result"] is None
    mock_task.delay.assert_not_called()
    mock_collect.assert_not_called()


def test_playlists_swallows_per_playlist_exceptions(client, mock_sp):
    mock_sp.current_user.return_value = {"id": "user1"}
    mock_sp.current_user_playlists.return_value = {
        "items": [_accessible_playlist(owner_id="user1")]
    }

    with patch("api.snapshots") as mock_snapshots, \
         patch("api.collect_tracks", side_effect=RuntimeError("spotify blew up")):
        mock_snapshots.is_up_to_date.return_value = False
        mock_snapshots.is_processing.return_value = False

        resp = client.get("/playlists")

    item = resp.json()["items"][0]
    assert item["job_id"] is None
    assert item["result"] is None
    assert item["total_tracks"] == 0


# ── /playlists/status (batch) ────────────────────────────────────────────

def test_playlist_status_done_returns_result(client):
    with patch("api.AsyncResult") as mock_ar:
        mock_ar.return_value.state = "SUCCESS"
        mock_ar.return_value.get.return_value = {"total_ingested": 5}

        resp = client.get("/playlists/status?job_ids=job1")

    assert resp.json() == {"items": {"job1": {"state": "done", "result": {"total_ingested": 5}}}}


def test_playlist_status_failure(client):
    with patch("api.AsyncResult") as mock_ar:
        mock_ar.return_value.state = "FAILURE"

        resp = client.get("/playlists/status?job_ids=job1")

    assert resp.json() == {"items": {"job1": {"state": "error"}}}


def test_playlist_status_pending_by_default(client):
    with patch("api.AsyncResult") as mock_ar:
        mock_ar.return_value.state = "PENDING"

        resp = client.get("/playlists/status?job_ids=job1")

    assert resp.json() == {"items": {"job1": {"state": "pending"}}}

def test_playlist_status_batch_handles_multiple_jobs_with_mixed_states(client):
    def fake_async_result(job_id, app):
        mock = MagicMock()
        if job_id == "job1":
            mock.state = "SUCCESS"
            mock.get.return_value = {"total_ingested": 5}
        elif job_id == "job2":
            mock.state = "FAILURE"
        else:  # job3
            mock.state = "PENDING"
        return mock

    with patch("api.AsyncResult", side_effect=fake_async_result):
        resp = client.get("/playlists/status?job_ids=job1,job2,job3")

    assert resp.json() == {
        "items": {
            "job1": {"state": "done", "result": {"total_ingested": 5}},
            "job2": {"state": "error"},
            "job3": {"state": "pending"},
        }
    }


def test_playlist_status_batch_empty_job_ids_returns_empty_items(client):
    resp = client.get("/playlists/status?job_ids=")
    assert resp.json() == {"items": {}}

# ── /track-search ─────────────────────────────────────────────────────────

def test_track_search_empty_query_skips_spotify_call(client, mock_sp):
    resp = client.get("/track-search?q=")
    assert resp.json() == {"items": []}
    mock_sp.search.assert_not_called()


def test_track_search_dedupes_same_name_and_artist(client, mock_sp):
    mock_sp.search.return_value = {
        "tracks": {"items": [
            {"id": "1", "name": "Song", "artists": [{"name": "Artist"}], "album": {"name": "A"}, "duration_ms": 1000},
            {"id": "2", "name": "song", "artists": [{"name": "artist"}], "album": {"name": "A"}, "duration_ms": 1000},
            {"id": "3", "name": "Other Song", "artists": [{"name": "Artist"}], "album": {"name": "A"}, "duration_ms": 1000},
        ]}
    }

    resp = client.get("/track-search?q=song")

    items = resp.json()["items"]
    assert len(items) == 2
    assert [i["id"] for i in items] == ["1", "3"]


def test_track_search_caps_results_at_five(client, mock_sp):
    mock_sp.search.return_value = {
        "tracks": {"items": [
            {"id": str(i), "name": f"Song {i}", "artists": [{"name": "A"}], "album": {"name": "X"}, "duration_ms": 1}
            for i in range(10)
        ]}
    }

    resp = client.get("/track-search?q=song")

    assert len(resp.json()["items"]) == 5


# ── /search ───────────────────────────────────────────────────────────────

def _search_payload(**overrides):
    payload = {
        "track_id": "t1",
        "track_name": "Song",
        "artist_name": "Artist",
        "album_name": "Album",
        "duration_ms": 200000,
        "playlists": [{"playlist_id": "pl1", "track_ids": ["a", "b"]}],
    }
    payload.update(overrides)
    return payload


def test_search_returns_scored_results_per_playlist(client):
    with patch("api.similarity_processor") as mock_sim:
        mock_sim.get_query_vector.return_value = [0.1, 0.2]
        mock_sim.score_playlist.return_value = ([{"name": "T", "artist": "A", "score": 80.0}], 75.0)

        resp = client.post("/search", json=_search_payload())

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results["pl1"]["mean"] == 75.0
    assert results["pl1"]["top5"][0]["name"] == "T"


def test_search_returns_500_on_processing_error(client):
    with patch("api.similarity_processor") as mock_sim:
        mock_sim.get_query_vector.side_effect = RuntimeError("download failed")

        resp = client.post("/search", json=_search_payload())

    assert resp.status_code == 500
    assert "download failed" in resp.json()["detail"]


def test_search_rejects_malformed_payload(client):
    resp = client.post("/search", json={"track_id": "t1"})  # missing required fields
    assert resp.status_code == 422

# ── POST /playlists/{playlist_id}/tracks ────────────────────────────────────

def test_add_track_to_playlist_success(client, mock_sp):
    mock_sp.playlist_add_items.return_value = {"snapshot_id": "new_snap"}

    resp = client.post("/playlists/pl1/tracks", json={"track_id": "trk1"})

    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    mock_sp.playlist_add_items.assert_called_once_with("pl1", ["trk1"])


def test_add_track_to_playlist_returns_500_on_spotify_error(client, mock_sp):
    mock_sp.playlist_add_items.side_effect = Exception("spotify rejected request")

    resp = client.post("/playlists/pl1/tracks", json={"track_id": "trk1"})

    assert resp.status_code == 500
    assert "spotify rejected request" in resp.json()["detail"]


def test_add_track_to_playlist_rejects_missing_track_id(client, mock_sp):
    resp = client.post("/playlists/pl1/tracks", json={})
    assert resp.status_code == 422
    mock_sp.playlist_add_items.assert_not_called()

# ── /me ───────────────────────────────────────────────────────────────────

def _top_artist(name="Artist A", image_url="https://img/a.jpg"):
    return {
        "name": name,
        "images": [{"url": image_url}] if image_url else [],
    }


def _top_track(name="Song A", artist="Artist A", image_url="https://img/t.jpg"):
    return {
        "name": name,
        "artists": [{"name": artist}] if artist else [],
        "album": {"images": [{"url": image_url}] if image_url else []},
    }


def _me_payload(**overrides):
    payload = {
        "id": "user1",
        "display_name": "Test User",
        "email": "test@example.com",
        "followers": {"total": 42},
        "product": "premium",
        "images": [{"url": "https://img/avatar.jpg"}],
        "external_urls": {"spotify": "https://open.spotify.com/user/user1"},
    }
    payload.update(overrides)
    return payload


def test_me_returns_full_profile(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload()
    mock_sp.current_user_playlists.return_value = {
        "items": [
            {"owner": {"id": "user1"}},
            {"owner": {"id": "someone_else"}},
        ],
        "next": None,
    }
    mock_sp.current_user_top_artists.return_value = {"items": [_top_artist()]}
    mock_sp.current_user_top_tracks.return_value = {"items": [_top_track()]}

    resp = client.get("/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "user1"
    assert body["display_name"] == "Test User"
    assert body["email"] == "test@example.com"
    assert body["followers"] == 42
    assert body["product"] == "premium"
    assert body["image_url"] == "https://img/avatar.jpg"
    assert body["spotify_url"] == "https://open.spotify.com/user/user1"
    assert body["owned_playlists"] == 1
    assert body["top_artists"] == [{"name": "Artist A", "image_url": "https://img/a.jpg"}]
    assert body["top_tracks"] == [{"name": "Song A", "artist": "Artist A", "image_url": "https://img/t.jpg"}]

    mock_sp.current_user_top_artists.assert_called_once_with(limit=10, time_range="medium_term")
    mock_sp.current_user_top_tracks.assert_called_once_with(limit=10, time_range="medium_term")


def test_me_counts_owned_playlists_across_pagination(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload()

    page1 = {
        "items": [{"owner": {"id": "user1"}}, {"owner": {"id": "other"}}],
        "next": "page2-token",
    }
    page2 = {
        "items": [{"owner": {"id": "user1"}}, {"owner": {"id": "user1"}}],
        "next": None,
    }
    mock_sp.current_user_playlists.return_value = page1
    mock_sp.next.side_effect = [page2]
    mock_sp.current_user_top_artists.return_value = {"items": []}
    mock_sp.current_user_top_tracks.return_value = {"items": []}

    resp = client.get("/me")

    assert resp.json()["owned_playlists"] == 3
    mock_sp.next.assert_called_once_with(page1)


def test_me_handles_missing_images_gracefully(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload(images=[])
    mock_sp.current_user_playlists.return_value = {"items": [], "next": None}
    mock_sp.current_user_top_artists.return_value = {"items": [_top_artist(image_url=None)]}
    mock_sp.current_user_top_tracks.return_value = {"items": [_top_track(image_url=None)]}

    resp = client.get("/me")

    body = resp.json()
    assert body["image_url"] is None
    assert body["top_artists"][0]["image_url"] is None
    assert body["top_tracks"][0]["image_url"] is None


def test_me_handles_no_followers_or_product(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload(followers=None, product=None)
    mock_sp.current_user_playlists.return_value = {"items": [], "next": None}
    mock_sp.current_user_top_artists.return_value = {"items": []}
    mock_sp.current_user_top_tracks.return_value = {"items": []}

    resp = client.get("/me")

    body = resp.json()
    assert body["followers"] is None
    assert body["product"] is None


def test_me_swallows_top_artists_failure(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload()
    mock_sp.current_user_playlists.return_value = {"items": [], "next": None}
    mock_sp.current_user_top_artists.side_effect = Exception("no user-top-read scope")
    mock_sp.current_user_top_tracks.return_value = {"items": [_top_track()]}

    resp = client.get("/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["top_artists"] == []
    assert len(body["top_tracks"]) == 1  # unaffected by the top-artists failure


def test_me_swallows_top_tracks_failure(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload()
    mock_sp.current_user_playlists.return_value = {"items": [], "next": None}
    mock_sp.current_user_top_artists.return_value = {"items": [_top_artist()]}
    mock_sp.current_user_top_tracks.side_effect = Exception("no user-top-read scope")

    resp = client.get("/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["top_tracks"] == []
    assert len(body["top_artists"]) == 1  # unaffected by the top-tracks failure


def test_me_swallows_owned_playlist_count_failure(client, mock_sp):
    mock_sp.current_user.return_value = _me_payload()
    mock_sp.current_user_playlists.side_effect = Exception("playlists unavailable")
    mock_sp.current_user_top_artists.return_value = {"items": []}
    mock_sp.current_user_top_tracks.return_value = {"items": []}

    resp = client.get("/me")

    assert resp.status_code == 200
    assert resp.json()["owned_playlists"] == 0


def test_me_returns_500_when_current_user_fails(client, mock_sp):
    mock_sp.current_user.side_effect = Exception("token expired")

    resp = client.get("/me")

    assert resp.status_code == 500
    assert "token expired" in resp.json()["detail"]
    # a failure fetching the base profile shouldn't attempt any follow-up calls
    mock_sp.current_user_playlists.assert_not_called()
    mock_sp.current_user_top_artists.assert_not_called()