"""
Tests for methods/playlists.py
"""
from unittest.mock import patch, MagicMock

import pytest

from methods.similarity import MEANS
from methods.playlists import (
    process_single_playlist,
    get_playlist_recommendations,
    process_tracks,
    process_one,
)

# ── fake redis lock helpers ─────────────────────────────────────────────────

class _FakeLock:
    def __init__(self, acquired=True):
        self._acquired = acquired
        self.released = False

    def acquire(self, blocking=True):
        return self._acquired

    def release(self):
        self.released = True


class _FakeRedisClient:
    """Stand-in for methods.locks.redis_client."""
    def __init__(self, acquired=True):
        self._acquired = acquired
        self.locks_created = []

    def lock(self, name, **kwargs):
        lock = _FakeLock(self._acquired)
        self.locks_created.append((name, lock))
        return lock


@pytest.fixture(autouse=True)
def uncontended_lock():
    """Every test in this file gets an always-acquired fake lock by default,
    so none of them hit a real Redis."""
    with patch("methods.playlists.redis_client", _FakeRedisClient(acquired=True)):
        yield


# ── helpers: a synchronous stand-in for ProcessPoolExecutor ────────────────

class _FakeFuture:
    def __init__(self, result=None, exception=None):
        self._result = result
        self._exception = exception

    def result(self):
        if self._exception is not None:
            raise self._exception
        return self._result


class _FakeExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def submit(self, fn, arg):
        try:
            return _FakeFuture(result=fn(arg))
        except Exception as e:  # pragma: no cover - defensive
            return _FakeFuture(exception=e)


def _identity_as_completed(futures_dict):
    return list(futures_dict.keys())


# ── process_tracks ───────────────────────────────────────────────────────────

def test_process_tracks_counts_successful_results():
    tracks = [{"id": f"id{i}", "name": f"t{i}"} for i in range(3)]

    def fake_process_one(track):
        return (track["id"], [1.0], {"name": track["name"]})

    with patch("methods.playlists.ProcessPoolExecutor", _FakeExecutor), \
         patch("methods.playlists.as_completed", _identity_as_completed), \
         patch("methods.playlists.process_one", side_effect=fake_process_one), \
         patch("methods.playlists.upsert_batch_of_tracks", return_value=True) as mock_upsert:
        total = process_tracks(tracks)

    assert total == 3
    mock_upsert.assert_called_once()


def test_process_tracks_skips_none_results():
    tracks = [{"id": "id1", "name": "ok"}, {"id": "id2", "name": "failed"}]

    def fake_process_one(track):
        return None if track["id"] == "id2" else (track["id"], [1.0], {})

    with patch("methods.playlists.ProcessPoolExecutor", _FakeExecutor), \
         patch("methods.playlists.as_completed", _identity_as_completed), \
         patch("methods.playlists.process_one", side_effect=fake_process_one), \
         patch("methods.playlists.upsert_batch_of_tracks", return_value=True):
        total = process_tracks(tracks)

    assert total == 1


def test_process_tracks_swallows_future_exceptions():
    tracks = [{"id": "id1", "name": "raises"}, {"id": "id2", "name": "ok"}]

    def fake_process_one(track):
        if track["id"] == "id1":
            raise RuntimeError("worker crashed")
        return (track["id"], [1.0], {})

    with patch("methods.playlists.ProcessPoolExecutor", _FakeExecutor), \
         patch("methods.playlists.as_completed", _identity_as_completed), \
         patch("methods.playlists.process_one", side_effect=fake_process_one), \
         patch("methods.playlists.upsert_batch_of_tracks", return_value=True):
        total = process_tracks(tracks)  # should not raise

    assert total == 1


def test_process_tracks_flushes_in_batches_of_100():
    tracks = [{"id": f"id{i}", "name": f"t{i}"} for i in range(150)]

    def fake_process_one(track):
        return (track["id"], [1.0], {})

    with patch("methods.playlists.ProcessPoolExecutor", _FakeExecutor), \
         patch("methods.playlists.as_completed", _identity_as_completed), \
         patch("methods.playlists.process_one", side_effect=fake_process_one), \
         patch("methods.playlists.upsert_batch_of_tracks", return_value=True) as mock_upsert:
        total = process_tracks(tracks)

    assert total == 150
    # one flush at 100, one final flush for the remaining 50
    assert mock_upsert.call_count == 2


# ── process_one ──────────────────────────────────────────────────────────────

def test_process_one_returns_tuple_on_success():
    track = {"id": "id1", "name": "Song", "artist": "Artist", "album": "Album", "duration_ms": 1000}

    with patch("methods.playlists.download_track") as mock_download, \
         patch("methods.playlists.ingest_song", return_value=[1.0, 2.0]), \
         patch("os.path.exists", return_value=False):
        result = process_one(track)

    assert result == ("id1", [1.0, 2.0], {
        "name": "Song", "artist": "Artist", "album": "Album", "duration_ms": 1000,
    })
    mock_download.assert_called_once_with("id1", "Song", "Artist", 1000)


def test_process_one_returns_none_on_timeout():
    track = {"id": "id1", "name": "Song", "artist": "Artist"}

    with patch("methods.playlists.download_track", side_effect=TimeoutError("too slow")), \
         patch("os.path.exists", return_value=False):
        result = process_one(track)

    assert result is None


def test_process_one_returns_none_on_generic_exception():
    track = {"id": "id1", "name": "Song", "artist": "Artist"}

    with patch("methods.playlists.download_track", side_effect=RuntimeError("network error")), \
         patch("os.path.exists", return_value=False):
        result = process_one(track)

    assert result is None


def test_process_one_cleans_up_temp_file():
    track = {"id": "id1", "name": "Song", "artist": "Artist"}

    with patch("methods.playlists.download_track"), \
         patch("methods.playlists.ingest_song", return_value=[1.0]), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove:
        process_one(track)

    mock_remove.assert_called_once_with("temp/id1.mp3")


# ── get_playlist_recommendations ────────────────────────────────────────────

def test_get_playlist_recommendations_empty_track_ids_returns_empty():
    result = get_playlist_recommendations([])
    assert result == []


def test_get_playlist_recommendations_returns_empty_when_no_vectors_found():
    with patch("methods.playlists.fetch_vectors_for_ids", return_value={}):
        result = get_playlist_recommendations(["id1", "id2"])
    assert result == []


def test_get_playlist_recommendations_excludes_existing_playlist_tracks():
    track_ids = ["id1", "id2"]
    existing_vectors = {
        "id1": {"values": MEANS.tolist(), "metadata": {}},
        "id2": {"values": MEANS.tolist(), "metadata": {}},
    }

    match_in_playlist = MagicMock(id="id1")
    match_new = MagicMock(id="id3")

    calls = {"fetch": []}

    def fake_fetch(ids):
        calls["fetch"].append(list(ids))
        if set(ids) == set(track_ids):
            return existing_vectors
        return {"id3": {"values": MEANS.tolist(), "metadata": {"name": "New", "artist": "A"}}}

    with patch("methods.playlists.fetch_vectors_for_ids", side_effect=fake_fetch), \
         patch("methods.playlists.query_similar", return_value=[match_in_playlist, match_new]) as mock_query:
        result = get_playlist_recommendations(track_ids)

    # candidate fetch should only have asked for id3, not id1 (already in playlist)
    assert calls["fetch"][1] == ["id3"]
    assert len(result) == 1
    assert result[0]["name"] == "New"


def test_get_playlist_recommendations_caps_top_k_at_1000():
    track_ids = [f"id{i}" for i in range(2000)]
    existing_vectors = {tid: {"values": MEANS.tolist(), "metadata": {}} for tid in track_ids}

    with patch("methods.playlists.fetch_vectors_for_ids", side_effect=[existing_vectors, {}]), \
         patch("methods.playlists.query_similar", return_value=[]) as mock_query:
        get_playlist_recommendations(track_ids)

    assert mock_query.call_args.kwargs["top_k"] == 1000


def test_get_playlist_recommendations_returns_top_3_sorted_desc():
    track_ids = ["id1"]
    existing_vectors = {"id1": {"values": MEANS.tolist(), "metadata": {}}}

    candidates = {
        "close": {"values": MEANS.tolist(), "metadata": {"name": "close", "artist": "a"}},
        "mid": {"values": (MEANS + 10).tolist(), "metadata": {"name": "mid", "artist": "a"}},
        "far": {"values": (MEANS + 100).tolist(), "metadata": {"name": "far", "artist": "a"}},
        "extra": {"values": (MEANS + 200).tolist(), "metadata": {"name": "extra", "artist": "a"}},
    }
    matches = [MagicMock(id=tid) for tid in candidates]

    with patch("methods.playlists.fetch_vectors_for_ids", side_effect=[existing_vectors, candidates]), \
         patch("methods.playlists.query_similar", return_value=matches):
        result = get_playlist_recommendations(track_ids)

    assert len(result) == 3
    assert [r["name"] for r in result] == ["close", "mid", "far"]


# ── process_single_playlist ─────────────────────────────────────────────────

def test_process_single_playlist_combines_cached_and_new_counts():
    track_ids = ["id1", "id2", "id3"]
    serializable_tracks = [{"id": tid, "name": tid} for tid in track_ids]

    with patch("methods.playlists.fetch_already_ingested", return_value={"id1"}), \
         patch("methods.playlists.process_tracks", return_value=2) as mock_process_tracks, \
         patch("methods.playlists.get_playlist_recommendations", return_value=[]):
        result = process_single_playlist("pl1", track_ids, serializable_tracks)

    # 2 newly processed + 1 already cached = 3
    assert result["total_ingested"] == 3
    # only the non-cached track should have been passed to process_tracks
    passed_tracks = mock_process_tracks.call_args.args[0]
    assert [t["id"] for t in passed_tracks] == ["id2", "id3"]


def test_process_single_playlist_swallows_recommendation_errors():
    track_ids = ["id1"]
    serializable_tracks = [{"id": "id1", "name": "id1"}]

    with patch("methods.playlists.fetch_already_ingested", return_value=set()), \
         patch("methods.playlists.process_tracks", return_value=1), \
         patch("methods.playlists.get_playlist_recommendations", side_effect=RuntimeError("pinecone down")):
        result = process_single_playlist("pl1", track_ids, serializable_tracks)

    assert result["recommendations"] == []


def test_process_single_playlist_returns_track_ids_unchanged():
    track_ids = ["id1", "id2"]
    serializable_tracks = [{"id": tid, "name": tid} for tid in track_ids]

    with patch("methods.playlists.fetch_already_ingested", return_value=set()), \
         patch("methods.playlists.process_tracks", return_value=2), \
         patch("methods.playlists.get_playlist_recommendations", return_value=[]):
        result = process_single_playlist("pl1", track_ids, serializable_tracks)

    assert result["track_ids"] == track_ids

def test_process_one_skips_when_lock_held_by_sibling_and_track_appears():
    track = {"id": "id1", "name": "Song", "artist": "Artist"}
    fake_client = _FakeRedisClient(acquired=False)

    with patch("methods.playlists.redis_client", fake_client), \
         patch("methods.playlists.time.sleep"), \
         patch("methods.playlists.fetch_vectors_for_ids", return_value={"id1": {}}), \
         patch("methods.playlists.download_track") as mock_download:
        result = process_one(track)

    assert result is None
    mock_download.assert_not_called()  # never raced the sibling's download


def test_process_one_gives_up_when_lock_held_and_track_never_appears():
    track = {"id": "id1", "name": "Song", "artist": "Artist"}
    fake_client = _FakeRedisClient(acquired=False)

    with patch("methods.playlists.redis_client", fake_client), \
         patch("methods.playlists.time.sleep"), \
         patch("methods.playlists.fetch_vectors_for_ids", return_value={}), \
         patch("methods.playlists.download_track") as mock_download:
        result = process_one(track)

    assert result is None
    mock_download.assert_not_called()


def test_process_one_releases_lock_after_success():
    track = {"id": "id1", "name": "Song", "artist": "Artist", "album": "Album", "duration_ms": 1000}
    fake_client = _FakeRedisClient(acquired=True)

    with patch("methods.playlists.redis_client", fake_client), \
         patch("methods.playlists.download_track"), \
         patch("methods.playlists.ingest_song", return_value=[1.0]), \
         patch("os.path.exists", return_value=False):
        process_one(track)

    _, lock = fake_client.locks_created[0]
    assert lock.released is True


def test_process_one_releases_lock_after_ingest_failure():
    track = {"id": "id1", "name": "Song", "artist": "Artist"}
    fake_client = _FakeRedisClient(acquired=True)

    with patch("methods.playlists.redis_client", fake_client), \
         patch("methods.playlists.download_track", side_effect=RuntimeError("boom")), \
         patch("os.path.exists", return_value=False):
        process_one(track)

    _, lock = fake_client.locks_created[0]
    assert lock.released is True  # released even though ingest raised


def test_process_one_locks_on_track_id_specifically():
    track = {"id": "unique-track-id", "name": "Song", "artist": "Artist"}
    fake_client = _FakeRedisClient(acquired=True)

    with patch("methods.playlists.redis_client", fake_client), \
         patch("methods.playlists.download_track"), \
         patch("methods.playlists.ingest_song", return_value=[1.0]), \
         patch("os.path.exists", return_value=False):
        process_one(track)

    lock_name, _ = fake_client.locks_created[0]
    assert lock_name == "ingest:unique-track-id"