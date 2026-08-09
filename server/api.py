from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from celery.result import AsyncResult
from celery_app import app as celery_app
from tasks import process_playlist_task
import traceback
from methods import similarity as similarity_processor
from methods import snapshots
from methods.playlists import get_playlist_recommendations

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
snapshots.init_db()

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="playlist-read-private playlist-read-collaborative playlist-modify-private playlist-modify-public"
))

@app.get("/login")
def login():
    auth_url = sp.auth_manager.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback")
def callback(code: str):
    sp.auth_manager.get_access_token(code)
    return RedirectResponse("http://localhost:5173/home")

def collect_tracks(sp, playlist_id):
    track_ids = []
    serializable_tracks = []

    results = sp.playlist_items(playlist_id)
    while results:
        for item in results['items']:
            track = item.get('item')
            if not track or not track.get('id'):
                continue
            artists = track.get('artists') or []
            artist_name = artists[0].get('name', '') if artists else ''
            album = track.get('album') or {}

            track_ids.append(track['id'])
            serializable_tracks.append({
                'id': track['id'],
                'name': str(track.get('name') or ''),
                'artist': str(artist_name),
                'album': str(album.get('name') or ''),
                'duration_ms': int(track.get('duration_ms') or 0),
            })

        results = sp.next(results) if results.get('next') else None

    return track_ids, serializable_tracks

@app.get("/playlists")
def get_playlists():
    user_id = sp.current_user()["id"]
    playlists = sp.current_user_playlists()

    accessible = []
    for p in playlists["items"]:
        if p["owner"]["id"] == user_id:
            accessible.append(p)
            continue
        try:
            sp.playlist_tracks(p["id"], limit=1)
            accessible.append(p)
        except Exception:
            continue

    result_items = []
    for p in accessible:
        playlist_id = p["id"]
        snapshot_id = p["snapshot_id"]
        print(p["name"], snapshot_id)

        try:
            # snapshot is up to date
            row = snapshots.get_snapshot(playlist_id)
            if snapshots.is_up_to_date(row, snapshot_id):
                track_ids, _ = collect_tracks(sp, playlist_id)
                recommendations = get_playlist_recommendations(track_ids)
                result_items.append({
                    "id": playlist_id,
                    "name": p["name"],
                    "total_tracks": row["total_tracks"],
                    "job_id": None,
                    "result": {
                        "total_ingested": row["total_ingested"],
                        "recommendations": recommendations,
                        "track_ids": track_ids,
                    },
                })
                continue

            # a job for this snapshot is already running — don't create another
            if snapshots.is_processing(row, snapshot_id):
                result_items.append({
                    "id": playlist_id,
                    "name": p["name"],
                    "total_tracks": row["total_tracks"] or 0,
                    "job_id": row["job_id"],
                    "result": None,
                })
                continue

            track_ids, serializable_tracks = collect_tracks(sp, playlist_id)
            print(f"{p['name']}: {len(track_ids)} tracks collected")
            job = process_playlist_task.delay(playlist_id, track_ids, serializable_tracks, snapshot_id)
            snapshots.mark_processing(playlist_id, snapshot_id, job.id, len(track_ids))
            result_items.append({
                "id": playlist_id,
                "name": p["name"],
                "total_tracks": len(track_ids),
                "job_id": job.id,
                "result": None,
            })
        except Exception as e:
            print(f"Skipping {p['name']}: {e}")
            result_items.append({
                "id": playlist_id,
                "name": p["name"],
                "total_tracks": 0,
                "job_id": None,
                "result": None,
            })

    return {"items": result_items}

@app.get("/playlists/status")
def playlists_status_batch(job_ids: str):
    ids = [j for j in job_ids.split(",") if j]
    items = {}
    for job_id in ids:
        result = AsyncResult(job_id, app=celery_app)
        if result.state == 'SUCCESS':
            items[job_id] = {"state": "done", "result": result.get()}
        elif result.state == 'FAILURE':
            items[job_id] = {"state": "error"}
        else:
            items[job_id] = {"state": "pending"}
    return {"items": items}

@app.get("/track-search")
def track_search(q: str):
    if not q.strip():
        return {"items": []}

    results = sp.search(q=q, type="track", limit=10)

    seen = set()
    items = []

    for t in results["tracks"]["items"]:
        key = (
            t["name"].lower().strip(),
            t["artists"][0]["name"].lower().strip()
        )
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": t["id"],
            "name": t["name"],
            "artist": t["artists"][0]["name"],
            "album": t["album"]["name"],
            "duration_ms": t["duration_ms"],
        })
        if len(items) == 5:
            break

    return {"items": items}

class PlaylistEntry(BaseModel):
    playlist_id: str
    track_ids: list[str]


class SearchQuery(BaseModel):
    track_id: str
    track_name: str
    artist_name: str
    album_name: str | None = None
    duration_ms: int | None = None
    playlists: list[PlaylistEntry]

@app.post("/search")
def search_song(query: SearchQuery):
    try:
        query_vector = similarity_processor.get_query_vector(
            query.track_id, query.track_name, query.artist_name,
            query.duration_ms, query.album_name
        )
        results = {}
        for entry in query.playlists:
            top5, mean = similarity_processor.score_playlist(query_vector, entry.track_ids)
            results[entry.playlist_id] = {"top5": top5, "mean": mean}

        return {"results": results}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class AddTrackRequest(BaseModel):
    track_id: str

@app.post("/playlists/{playlist_id}/tracks")
def add_track_to_playlist(playlist_id: str, body: AddTrackRequest):
    try:
        sp.playlist_add_items(playlist_id, [body.track_id])
        return {"success": True}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))