from celery_app import app
from methods.playlists import process_single_playlist
from methods import snapshots


@app.task
def process_playlist_task(playlist_id, track_ids, serializable_tracks, snapshot_id):
    result = process_single_playlist(playlist_id, track_ids, serializable_tracks)

    # only marks 'done' if every track for this snapshot is ingested
    snapshots.mark_result(
        playlist_id,
        snapshot_id,
        total_tracks=len(track_ids),
        total_ingested=result["total_ingested"],
        track_ids=result["track_ids"],
        recommendations=result["recommendations"],
    )

    return result