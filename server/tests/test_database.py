"""
Tests for methods/database.py
"""
from unittest.mock import patch, MagicMock

from methods.database import (
    upsert_track,
    upsert_batch_of_tracks,
    fetch_already_ingested,
    fetch_vectors_for_ids,
    query_similar,
)


# ── upsert_track ─────────────────────────────────────────────────────────────

def test_upsert_track_calls_index_with_expected_payload():
    with patch("methods.database.index") as mock_index:
        mock_index.upsert.return_value = {"upserted_count": 1}
        result = upsert_track("id1", [0.1, 0.2], {"name": "Song"})

    mock_index.upsert.assert_called_once_with(vectors=[
        {"id": "id1", "values": [0.1, 0.2], "metadata": {"name": "Song"}}
    ])
    assert result == {"upserted_count": 1}


def test_upsert_track_returns_none_on_exception():
    with patch("methods.database.index") as mock_index:
        mock_index.upsert.side_effect = Exception("network error")
        result = upsert_track("id1", [0.1], {})

    assert result is None


# ── upsert_batch_of_tracks ───────────────────────────────────────────────────

def test_upsert_batch_of_tracks_builds_vectors_list():
    records = [
        ("id1", [0.1], {"name": "a"}),
        ("id2", [0.2], {"name": "b"}),
    ]
    with patch("methods.database.index") as mock_index:
        upsert_batch_of_tracks(records)

    called_vectors = mock_index.upsert.call_args.kwargs["vectors"]
    assert called_vectors == [
        {"id": "id1", "values": [0.1], "metadata": {"name": "a"}},
        {"id": "id2", "values": [0.2], "metadata": {"name": "b"}},
    ]


def test_upsert_batch_of_tracks_returns_none_on_exception():
    with patch("methods.database.index") as mock_index:
        mock_index.upsert.side_effect = Exception("boom")
        result = upsert_batch_of_tracks([("id1", [0.1], {})])

    assert result is None


# ── fetch_already_ingested ───────────────────────────────────────────────────

def test_fetch_already_ingested_empty_input_skips_network_call():
    with patch("methods.database.index") as mock_index:
        result = fetch_already_ingested([])

    assert result == set()
    mock_index.fetch.assert_not_called()


def test_fetch_already_ingested_returns_ids_present_in_index():
    mock_result = MagicMock()
    mock_result.vectors = {"id1": MagicMock(), "id2": MagicMock()}
    with patch("methods.database.index") as mock_index:
        mock_index.fetch.return_value = mock_result
        result = fetch_already_ingested(["id1", "id2", "id3"])

    assert result == {"id1", "id2"}


def test_fetch_already_ingested_returns_empty_set_on_exception():
    with patch("methods.database.index") as mock_index:
        mock_index.fetch.side_effect = Exception("boom")
        result = fetch_already_ingested(["id1"])

    assert result == set()


# ── fetch_vectors_for_ids ────────────────────────────────────────────────────

def _vec_obj(values, metadata):
    obj = MagicMock()
    obj.values = values
    obj.metadata = metadata
    return obj


def test_fetch_vectors_for_ids_empty_input_skips_network_call():
    with patch("methods.database.index") as mock_index:
        result = fetch_vectors_for_ids([])

    assert result == {}
    mock_index.fetch.assert_not_called()


def test_fetch_vectors_for_ids_chunks_requests_by_1000():
    track_ids = [f"id{i}" for i in range(2500)]

    def fake_fetch(ids):
        res = MagicMock()
        res.vectors = {tid: _vec_obj([1.0], {"name": tid}) for tid in ids}
        return res

    with patch("methods.database.index") as mock_index:
        mock_index.fetch.side_effect = fake_fetch
        result = fetch_vectors_for_ids(track_ids)

    assert mock_index.fetch.call_count == 3  # ceil(2500 / 1000)
    assert len(result) == 2500
    assert result["id0"] == {"values": [1.0], "metadata": {"name": "id0"}}


def test_fetch_vectors_for_ids_continues_after_chunk_failure():
    track_ids = [f"id{i}" for i in range(1500)]  # 2 chunks

    call_count = {"n": 0}

    def fake_fetch(ids):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("chunk failed")
        res = MagicMock()
        res.vectors = {tid: _vec_obj([2.0], {"name": tid}) for tid in ids}
        return res

    with patch("methods.database.index") as mock_index:
        mock_index.fetch.side_effect = fake_fetch
        result = fetch_vectors_for_ids(track_ids)

    # first chunk (ids 0-999) failed, second chunk (ids 1000-1499) succeeded
    assert len(result) == 500
    assert "id0" not in result
    assert "id1000" in result


def test_fetch_vectors_for_ids_returns_empty_dict_on_outer_exception():
    with patch("methods.database.index") as mock_index:
        # os.path-like failure before the loop starts is unlikely, but
        # simulate a completely broken index object
        mock_index.fetch.side_effect = Exception("boom")
        result = fetch_vectors_for_ids(["id1"])

    assert result == {}


# ── query_similar ────────────────────────────────────────────────────────────

def test_query_similar_returns_matches():
    mock_result = MagicMock()
    mock_result.matches = ["match1", "match2"]
    with patch("methods.database.index") as mock_index:
        mock_index.query.return_value = mock_result
        result = query_similar([0.1, 0.2], top_k=10)

    mock_index.query.assert_called_once_with(vector=[0.1, 0.2], top_k=10, include_metadata=True)
    assert result == ["match1", "match2"]


def test_query_similar_returns_empty_list_on_exception():
    with patch("methods.database.index") as mock_index:
        mock_index.query.side_effect = Exception("boom")
        result = query_similar([0.1], top_k=5)

    assert result == []