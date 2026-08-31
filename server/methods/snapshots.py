import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "snapshots.db")

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

RECS_REFRESH_INTERVAL = timedelta(days=7)

@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL mode so the FastAPI process and Celery worker both read/write this file concurrently
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_snapshots (
                playlist_id     TEXT PRIMARY KEY,
                snapshot_id     TEXT NOT NULL,
                status          TEXT NOT NULL,
                job_id          TEXT,
                total_tracks    INTEGER,
                total_ingested  INTEGER,
                track_ids       TEXT,
                recommendations TEXT,
                updated_at      TEXT NOT NULL
            )
        """)


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_snapshot(playlist_id):
    """Returns the cached row for a playlist, or None if never seen."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM playlist_snapshots WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        return dict(row) if row else None


def is_up_to_date(row, snapshot_id):
    """True only if this exact snapshot was already fully ingested."""
    if row is None:
        return False
    return row["snapshot_id"] == snapshot_id and row["status"] == STATUS_DONE


def mark_processing(playlist_id, snapshot_id, job_id, total_tracks):
    """Called right after a Celery job is created. Overwrites any prior row for this playlist_id."""
    with _connect() as conn:
        conn.execute("""
            INSERT INTO playlist_snapshots
                (playlist_id, snapshot_id, status, job_id, total_tracks, total_ingested,
                 track_ids, recommendations, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
            ON CONFLICT(playlist_id) DO UPDATE SET
                snapshot_id = excluded.snapshot_id,
                status = excluded.status,
                job_id = excluded.job_id,
                total_tracks = excluded.total_tracks,
                total_ingested = NULL,
                track_ids = NULL,
                recommendations = NULL,
                updated_at = excluded.updated_at
        """, (playlist_id, snapshot_id, STATUS_PROCESSING, job_id, total_tracks, _now()))


def mark_result(playlist_id, snapshot_id, total_tracks, total_ingested,
                 track_ids=None, recommendations=None):
    """Called after process_single_playlist returns. Persists track_ids/recommendations
    alongside the status so a later 'up to date' check never has to recompute them."""
    status = STATUS_DONE if total_ingested == total_tracks else STATUS_FAILED
    with _connect() as conn:
        conn.execute("""
            UPDATE playlist_snapshots
            SET status = ?, total_ingested = ?, track_ids = ?, recommendations = ?, updated_at = ?
            WHERE playlist_id = ? AND snapshot_id = ?
        """, (
            status, total_ingested,
            json.dumps(track_ids or []),
            json.dumps(recommendations or []),
            _now(), playlist_id, snapshot_id,
        ))


def is_processing(row, snapshot_id):
    """True if a job for this exact snapshot is already in process."""
    if row is None:
        return False
    return row["snapshot_id"] == snapshot_id and row["status"] == STATUS_PROCESSING

def is_stale(row, interval=RECS_REFRESH_INTERVAL):
    """True if a 'done' row's recommendations haven't been refreshed in over
    `interval` — independent of whether the snapshot_id itself changed."""
    if row is None or not row.get("updated_at"):
        return False
    updated_at = datetime.fromisoformat(row["updated_at"])
    return (datetime.now(timezone.utc) - updated_at) > interval

def update_recommendations(playlist_id, snapshot_id, recommendations):
    """Refreshes just the cached recommendations for an already up-to-date
    snapshot. Bumps updated_at so the staleness clock resets."""
    with _connect() as conn:
        conn.execute("""
            UPDATE playlist_snapshots
            SET recommendations = ?, updated_at = ?
            WHERE playlist_id = ? AND snapshot_id = ?
        """, (json.dumps(recommendations or []), _now(), playlist_id, snapshot_id))