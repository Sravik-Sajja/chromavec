from celery_app import app
from methods.playlists import process_single_playlist

@app.task
def process_playlist_task(playlist_id, track_ids, serializable_tracks):
    return process_single_playlist(playlist_id, track_ids, serializable_tracks)