"""
Tests for methods/snapshots.py
"""
import pytest

from methods import snapshots


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point every test at its own throwaway sqlite file"""
    db_file = tmp_path / "test_snapshots.db"
    monkeypatch.setattr(snapshots, "DB_PATH", str(db_file))
    snapshots.init_db()
    yield


# ── get_snapshot / is_up_to_date on an unseen playlist ──────────────────────

def test_get_snapshot_returns_none_for_unknown_playlist():
    assert snapshots.get_snapshot("pl_unknown") is None


def test_is_up_to_date_false_when_never_seen():
    assert snapshots.is_up_to_date("pl1", "snap1") is False


def test_is_processing_false_when_never_seen():
    assert snapshots.is_processing("pl1", "snap1") is False


# ── mark_processing ──────────────────────────────────────────────────────────

def test_mark_processing_sets_processing_status():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)

    row = snapshots.get_snapshot("pl1")
    assert row["status"] == snapshots.STATUS_PROCESSING
    assert row["snapshot_id"] == "snap1"
    assert row["job_id"] == "job-1"
    assert row["total_tracks"] == 10
    assert row["total_ingested"] is None


def test_is_processing_true_for_matching_snapshot():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    assert snapshots.is_processing("pl1", "snap1") is True


def test_is_processing_false_for_different_snapshot():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    assert snapshots.is_processing("pl1", "snap2") is False


def test_is_up_to_date_false_while_still_processing():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    assert snapshots.is_up_to_date("pl1", "snap1") is False


def test_mark_processing_overwrites_prior_row_for_same_playlist():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    snapshots.mark_processing("pl1", "snap2", "job-2", total_tracks=12)

    row = snapshots.get_snapshot("pl1")
    assert row["snapshot_id"] == "snap2"
    assert row["job_id"] == "job-2"
    assert row["total_tracks"] == 12
    assert row["status"] == snapshots.STATUS_PROCESSING
    # a fresh snapshot has no ingestion result yet, even if the old one did
    assert row["total_ingested"] is None


# ── mark_result: done vs failed ──────────────────────────────────────────────

def test_mark_result_all_ingested_marks_done():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    snapshots.mark_result("pl1", "snap1", total_tracks=10, total_ingested=10)

    row = snapshots.get_snapshot("pl1")
    assert row["status"] == snapshots.STATUS_DONE
    assert row["total_ingested"] == 10
    assert snapshots.is_up_to_date("pl1", "snap1") is True


def test_mark_result_partial_ingest_marks_failed():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    snapshots.mark_result("pl1", "snap1", total_tracks=10, total_ingested=8)

    row = snapshots.get_snapshot("pl1")
    assert row["status"] == snapshots.STATUS_FAILED
    assert row["total_ingested"] == 8
    assert snapshots.is_up_to_date("pl1", "snap1") is False


def test_mark_result_zero_ingested_marks_failed():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=5)
    snapshots.mark_result("pl1", "snap1", total_tracks=5, total_ingested=0)

    row = snapshots.get_snapshot("pl1")
    assert row["status"] == snapshots.STATUS_FAILED


# ── race guard: a stale job shouldn't clobber a newer snapshot's row ────────

def test_mark_result_is_noop_if_snapshot_was_superseded():
    # job for snap1 starts...
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    # ...but the playlist changes again before it finishes, so a new job
    # for snap2 gets kicked off and overwrites the row
    snapshots.mark_processing("pl1", "snap2", "job-2", total_tracks=12)

    # the old job for snap1 finally finishes and reports its result
    snapshots.mark_result("pl1", "snap1", total_tracks=10, total_ingested=10)

    # row should still reflect snap2 (still processing), untouched by
    # the stale snap1 result
    row = snapshots.get_snapshot("pl1")
    assert row["snapshot_id"] == "snap2"
    assert row["status"] == snapshots.STATUS_PROCESSING
    assert row["job_id"] == "job-2"


def test_is_up_to_date_false_for_superseded_snapshot_even_if_it_was_done():
    snapshots.mark_processing("pl1", "snap1", "job-1", total_tracks=10)
    snapshots.mark_result("pl1", "snap1", total_tracks=10, total_ingested=10)
    assert snapshots.is_up_to_date("pl1", "snap1") is True  # sanity check

    # playlist changes again
    snapshots.mark_processing("pl1", "snap2", "job-2", total_tracks=11)

    # the old, once-"done" snapshot is no longer considered up to date
    assert snapshots.is_up_to_date("pl1", "snap1") is False


# ── isolation between playlists ──────────────────────────────────────────────

def test_different_playlists_tracked_independently():
    snapshots.mark_processing("pl1", "snapA", "job-1", total_tracks=5)
    snapshots.mark_result("pl1", "snapA", total_tracks=5, total_ingested=5)

    snapshots.mark_processing("pl2", "snapB", "job-2", total_tracks=3)

    assert snapshots.is_up_to_date("pl1", "snapA") is True
    assert snapshots.is_up_to_date("pl2", "snapB") is False
    assert snapshots.is_processing("pl2", "snapB") is True
    assert snapshots.is_processing("pl1", "snapA") is False


# ── WAL mode ──────────────────────────────────────────────────────────────────

def test_wal_mode_is_enabled():
    with snapshots._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"