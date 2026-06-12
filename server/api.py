from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from methods import playlists as playlists_processor
from methods import similarity as similarity_processor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="playlist-read-private playlist-read-collaborative"
))

@app.get("/login")
def login():
    auth_url = sp.auth_manager.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback")
def callback(code: str):
    sp.auth_manager.get_access_token(code)
    return RedirectResponse("http://localhost:5173/home")

@app.get("/playlists")
def get_playlists():
    playlists = sp.current_user_playlists()
    #playlists_processor.process_playlists(sp, playlists)
    return playlists

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
            "artist": t["artists"][0]["name"]
        })

        if len(items) == 5:
            break

    return {"items": items}


class SearchQuery(BaseModel):
    track_name: str
    artist_name: str

@app.post("/search")
def search_song(query: SearchQuery):
    track_name = query.track_name
    artist_name = query.artist_name
    track_id = f"search_{track_name + artist_name}"
    try:
        top5, mean = similarity_processor.get_playlist_similarity(track_id, track_name, artist_name)
        return {"top5": top5, "mean": mean}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))