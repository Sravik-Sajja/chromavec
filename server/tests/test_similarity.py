"""
Tests for methods/similarity.py
"""
import os
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from methods.similarity import (
    MEANS,
    STDS,
    weighted_cosine,
    get_query_vector,
    score_playlist,
)


# ── weighted_cosine ──────────────────────────────────────────────────────────

def test_weighted_cosine_identical_nonzero_z_vectors_is_one():
    # a vector offset from MEANS so its z-score isn't the zero vector
    v = (MEANS + 50).tolist()
    assert weighted_cosine(v, v) == pytest.approx(1.0, abs=1e-6)


def test_weighted_cosine_returns_zero_when_z_score_vector_is_zero():
    # feeding in exactly MEANS gives a z-scored vector of all zeros, which
    # hits the denom == 0 guard rather than producing a divide-by-zero error
    v = MEANS.tolist()
    assert weighted_cosine(v, v) == 0.0


def test_weighted_cosine_is_symmetric():
    rng = np.random.default_rng(0)
    v1 = (MEANS + rng.normal(scale=5, size=MEANS.shape)).tolist()
    v2 = (MEANS + rng.normal(scale=5, size=MEANS.shape)).tolist()
    assert weighted_cosine(v1, v2) == pytest.approx(weighted_cosine(v2, v1))


def test_weighted_cosine_score_in_valid_range():
    rng = np.random.default_rng(1)
    v1 = (MEANS + rng.normal(scale=5, size=MEANS.shape)).tolist()
    v2 = (MEANS + rng.normal(scale=5, size=MEANS.shape)).tolist()
    score = weighted_cosine(v1, v2)
    assert -1.0 - 1e-6 <= score <= 1.0 + 1e-6


def test_weighted_cosine_clips_extreme_outliers_without_error():
    # values wildly outside MEANS +/- 3*STDS should be clipped, not blow up
    v1 = (MEANS + 1e6).tolist()
    v2 = MEANS.tolist()
    score = weighted_cosine(v1, v2)
    assert np.isfinite(score)


# ── score_playlist ───────────────────────────────────────────────────────────

def test_score_playlist_returns_empty_when_no_stored_vectors():
    with patch("methods.similarity.fetch_vectors_for_ids", return_value={}):
        top5, mean = score_playlist(MEANS.tolist(), ["a", "b", "c"])
    assert top5 == []
    assert mean == 0.0


def _direction_vector(seed, scale=0.5):
    """A vector offset from MEANS along a fixed random direction, scaled in
    units of STDS."""
    rng = np.random.default_rng(seed)
    direction = rng.normal(size=len(MEANS))
    return direction, (MEANS + direction * STDS * scale).tolist()


def test_score_playlist_sorts_descending_and_returns_top5():
    direction, query = _direction_vector(seed=1, scale=0.5)
    close = (MEANS + direction * STDS * 0.6).tolist()   # same direction -> high similarity
    far = (MEANS - direction * STDS * 0.5).tolist()      # opposite direction -> low similarity

    stored = {
        "far": {"values": far, "metadata": {"name": "Far", "artist": "X"}},
        "close": {"values": close, "metadata": {"name": "Close", "artist": "Y"}},
    }
    with patch("methods.similarity.fetch_vectors_for_ids", return_value=stored):
        top5, mean = score_playlist(query, list(stored.keys()))

    assert [t["name"] for t in top5] == ["Close", "Far"]
    assert isinstance(mean, float)


def test_score_playlist_mean_is_over_top_half_only():
    # construct 4 tracks: 2 very similar to query, 2 very dissimilar.
    # mean should reflect only the top 2 (top half of 4), not all 4.
    direction, query = _direction_vector(seed=2, scale=0.5)
    close_vec = (MEANS + direction * STDS * 0.5).tolist()
    far_vec = (MEANS - direction * STDS * 0.5).tolist()

    stored = {
        "a": {"values": close_vec, "metadata": {"name": "a", "artist": "x"}},
        "b": {"values": close_vec, "metadata": {"name": "b", "artist": "x"}},
        "c": {"values": far_vec, "metadata": {"name": "c", "artist": "x"}},
        "d": {"values": far_vec, "metadata": {"name": "d", "artist": "x"}},
    }
    with patch("methods.similarity.fetch_vectors_for_ids", return_value=stored):
        _, mean = score_playlist(query, list(stored.keys()))

    # top half (a, b) are near-perfect matches to the query vector
    assert mean > 90.0


def test_score_playlist_returns_at_most_five_in_top5():
    stored = {
        f"id{i}": {"values": (MEANS + i).tolist(), "metadata": {"name": f"t{i}", "artist": "a"}}
        for i in range(8)
    }
    with patch("methods.similarity.fetch_vectors_for_ids", return_value=stored):
        top5, _ = score_playlist(MEANS.tolist(), list(stored.keys()))
    assert len(top5) == 5


# ── get_query_vector ─────────────────────────────────────────────────────────

def test_get_query_vector_returns_cached_values_without_downloading():
    cached = {"track1": {"values": [1, 2, 3], "metadata": {}}}
    with patch("methods.similarity.fetch_vectors_for_ids", return_value=cached), \
         patch("methods.similarity.download_track") as mock_download, \
         patch("methods.similarity.ingest_song") as mock_ingest:
        result = get_query_vector("track1", "Song", "Artist")

    assert result == [1, 2, 3]
    mock_download.assert_not_called()
    mock_ingest.assert_not_called()


def test_get_query_vector_downloads_and_ingests_on_cache_miss():
    with patch("methods.similarity.fetch_vectors_for_ids", return_value={}), \
         patch("methods.similarity.download_track") as mock_download, \
         patch("methods.similarity.ingest_song", return_value=[9, 9, 9]) as mock_ingest, \
         patch("methods.similarity.upsert_track") as mock_upsert, \
         patch("os.path.exists", return_value=False):
        result = get_query_vector("track2", "Song", "Artist", duration_ms=200000, album_name="Album")

    mock_download.assert_called_once_with("track2", "Song", "Artist", 200000)
    mock_ingest.assert_called_once_with("track2")
    mock_upsert.assert_called_once()
    assert result == [9, 9, 9]


def test_get_query_vector_cleans_up_temp_file_even_on_failure():
    with patch("methods.similarity.fetch_vectors_for_ids", return_value={}), \
         patch("methods.similarity.download_track"), \
         patch("methods.similarity.ingest_song", side_effect=RuntimeError("boom")), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove:
        with pytest.raises(RuntimeError):
            get_query_vector("track3", "Song", "Artist")

    mock_remove.assert_called_once_with("temp/track3.mp3")


def test_get_query_vector_swallows_upsert_failure():
    with patch("methods.similarity.fetch_vectors_for_ids", return_value={}), \
         patch("methods.similarity.download_track"), \
         patch("methods.similarity.ingest_song", return_value=[1, 1]), \
         patch("methods.similarity.upsert_track", side_effect=RuntimeError("pinecone down")), \
         patch("os.path.exists", return_value=False):
        result = get_query_vector("track4", "Song", "Artist")

    # upsert failing shouldn't prevent the vector from being returned
    assert result == [1, 1]