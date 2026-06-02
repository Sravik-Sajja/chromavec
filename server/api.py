from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from methods import playlists as playlists_processor

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
    playlists_processor.process_playlists(sp, playlists)
    return playlists