# PlaylistMatch

Find out which of your Spotify playlists a song *actually* fits — based on how it sounds, not just genre tags or metadata.

PlaylistMatch analyzes the raw audio of your Spotify playlists (chroma, timbre, spectral, and rhythm features) and lets you search for any song to see a similarity score against each of your playlists, plus the closest-matching tracks and new recommendations — with one click to add any recommendation straight to the matching playlist.

## How it works

1. **Connect Spotify** — the app authenticates via Spotify OAuth and pulls your accessible playlists.
2. **Ingest tracks** — each track is located on YouTube (via `yt-dlp`), downloaded as audio, and run through `librosa` to extract a feature vector: chroma STFT, MFCCs, spectral centroid, tempo, zero-crossing rate, and spectral rolloff. Vectors are cached in Pinecone so a track is only ever processed once.
3. **Search a song** — pick any track, and its feature vector is compared against every ingested playlist using a weighted, z-scored cosine similarity. Each playlist gets a match score, a top-5 breakdown, and "you might also like" recommendations pulled from the wider Pinecone index.
4. **Add recommendations back to Spotify** — searched songs and each "you might also like" track has an add button that writes the track directly to that playlist via the Spotify API.
5. **View your profile** — a profile icon in the top-right of the home screen opens a profile page showing your Spotify account info and profile data

Playlist ingestion happens asynchronously via Celery so the UI can show live progress while tracks download and process in the background. A local SQLite snapshot table tracks each playlist's Spotify `snapshot_id` so unchanged playlists skip re-ingestion entirely, and in-flight jobs aren't duplicated if the same playlist is requested again while still processing.

Both playlist ingestion state and profile data are cached client-side in React context, so navigating between the home and profile pages doesn't re-trigger loading states or refetch data that's already been fetched this session.

## Tech stack

**Backend**
- FastAPI — REST API
- Celery + Redis — background playlist ingestion
- Spotipy — Spotify Web API / OAuth
- yt-dlp + mutagen — locating and downloading audio
- librosa + numpy — audio feature extraction and similarity scoring
- Pinecone — vector storage and similarity search
- SQLite (WAL mode) — tracks per-playlist ingestion snapshots/status so the API and Celery worker can share state

**Frontend**
- React 19 + Vite
- React Router
- React Context — cross-page caching for playlist ingestion state and profile data

**Infra**
- Docker + Docker Compose — containerized local dev (API, Celery worker, Redis, client)

## Project structure

```
server/
  api.py                  FastAPI app: auth, playlists, search, profile endpoints
  celery_app.py           Celery app configuration
  tasks.py                Celery task definitions
  Dockerfile               Server image (shared by the API and worker containers)
  .dockerignore
  methods/
    playlists.py          Playlist ingestion + recommendations
    similarity.py          Feature scoring, means/stds/weights, query vectors
    metrics.py             librosa feature extraction (ingest_song)
    download.py             yt-dlp track downloading
    database.py             Pinecone read/write helpers
    snapshots.py             SQLite-backed playlist snapshot/status tracking (pending/processing/done/failed)
    locks.py
  evals/                   Offline rap-vs-pop separation evaluation
  tests/                   pytest suite

client/
  src/
    pages/                 Login, Home, and Profile pages
    context/                PlaylistsContext (ingestion state/polling) and ProfileContext (account data), both cached for the session
    styles/                Page styles
  Dockerfile               Client (Vite dev server) image
  .dockerignore
  vite.config.js

docker-compose.yml         Orchestrates redis, api, worker, and client together
```

## Getting started

You can run PlaylistMatch either with **Docker** (recommended — one command, no local Python/Node/Redis/ffmpeg install needed) or **manually**.

### Prerequisites (both methods)

- A [Spotify Developer](https://developer.spotify.com/dashboard) app (client ID/secret + redirect URI)
- A [Pinecone](https://www.pinecone.io/) account and index named `chromavec`

---

### Option A: Docker (recommended)

**Additional prerequisite:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Create a `.env` file in `server/`:

```
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
PINECONE_API_KEY=your_pinecone_api_key
```

> Register `http://localhost:8000/callback` as a redirect URI in your Spotify Developer Dashboard app settings, or OAuth will fail.

From the repo root:

```bash
docker compose up --build
```

This starts Redis, the FastAPI server, the Celery worker, and the Vite client together:

- Client: [http://localhost:5173](http://localhost:5173)
- API: [http://localhost:8000](http://localhost:8000)

Your local `server/` and `client/` source is mounted into the containers, so code changes hot-reload (`--reload` for the API, Vite's dev server for the client) without needing a rebuild. You only need to re-run `docker compose up --build` when you change `requirements.txt`, `package.json`, or a `Dockerfile` itself.

---

### Option B: Manual setup

**Additional prerequisites:**
- Python 3.12
- Node.js
- Redis (for Celery broker/backend)
- `ffmpeg` installed and on your `PATH` (required by `yt-dlp`/`mutagen` for audio extraction)

#### Backend setup

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in `server/`:

```
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
PINECONE_API_KEY=your_pinecone_api_key
```

Start Redis (if not already running):

```bash
redis-server
```

Start the Celery worker:

```bash
celery -A celery_app worker --loglevel=info --pool=threads
```

Start the API server:

```bash
uvicorn api:app --reload --port 8000
```

The API will create a local `snapshots.db` SQLite file (in `server/`) on first run to track playlist ingestion state — no setup required.

#### Frontend setup

```bash
cd client
npm install
npm run dev
```

Visit the client (default `http://localhost:5173`), connect your Spotify account, and search for a song once your playlists finish processing.

---

### Running tests

Tests run the same way whether or not you're using Docker — from inside the `server/` environment (either your local venv, or via `docker compose exec`):

```bash
cd server
pytest tests/ --ignore=tests/test_eval_script.py -v --cov=methods --cov-report=term-missing
```

Or, if you're using Docker and want to run them inside the running `api` container without a local Python install:

```bash
docker compose exec api pytest tests/ --ignore=tests/test_eval_script.py -v --cov=methods --cov-report=term-missing
```

`test_eval_script.py` runs a real end-to-end rap-vs-pop separation regression check and downloads live audio, so it's excluded from CI and run separately when needed:

```bash
pytest tests/test_eval_script.py -v
```

## API overview

| Endpoint | Description |
|---|---|
| `GET /login` | Redirects to Spotify's OAuth authorization page |
| `GET /callback` | Spotify OAuth callback, redirects to the client app |
| `GET /playlists` | Lists the user's accessible playlists. Returns cached ingestion results directly from the snapshot table for playlists whose snapshot is up to date (refreshing recommendations in the background if the cache is over a week old), reuses the in-flight job for playlists still processing, and kicks off a new async ingestion job otherwise |
| `GET /playlists/status?job_ids=` | Polls ingestion job status for one or more jobs at once (comma-separated IDs), returning per-job state (`pending`/`done`/`error`) keyed by job ID |
| `GET /track-search?q=` | Autocomplete search for a track via Spotify |
| `POST /search` | Scores a track against one or more ingested playlists |
| `POST /playlists/{playlist_id}/tracks` | Adds a track to the given Spotify playlist |
| `GET /me` | Returns the current user's Spotify profile info |

## Client-side caching

Two React contexts sit above the `/home` and `/profile` routes (see `client/src/context/`) so switching between pages doesn't re-trigger loading spinners or duplicate network requests:

- **`PlaylistsContext`** — owns the `/playlists` fetch, the ingestion-progress polling loop against `/playlists/status`, and per-playlist search results.
- **`ProfileContext`** — owns the `/me` fetch. It only runs once per session so bouncing back and forth between the two pages is instant after the first load.

Both contexts reset naturally when navigating back to `/` (login), since that's outside the layout route they're scoped to.

## Notes

- Audio is downloaded temporarily to `server/temp/` and deleted immediately after feature extraction.
- Both playlist match scores and "you might also like" recommendation scores are computed the same way: a track is scored against every individual track in the playlist, then averaged over the top half of those per-track scores (not a single averaged "playlist vector"). This avoids diluting genuinely close matches on stylistically mixed playlists, where a single centroid vector wouldn't represent any real track in the playlist.
- For playlists larger than 200 tracks, recommendation scoring samples 200 playlist tracks at random rather than scoring against every track, to bound the cost of scoring each of the ~1000 candidate tracks pulled from Pinecone. The initial candidate retrieval from Pinecone uses the full playlist's averaged vector.
- Playlist ingestion state (which Spotify `snapshot_id` was last processed, and whether it fully succeeded) is tracked in a local SQLite table (`methods/snapshots.py`) in WAL mode, shared between the FastAPI process and the Celery worker. A snapshot only counts as "done" if every track in it was successfully ingested; partial ingestion is marked "failed" so it gets retried on the next request.
- Adding a recommended track to a playlist calls the Spotify API directly and doesn't wait for re-ingestion — the playlist's `snapshot_id` will change as a result, so the next `/playlists` request will re-trigger ingestion for that playlist to pick up the new track.
- `server/evals/` contains a standalone script for sanity-checking that rap reference tracks score meaningfully higher against rap queries than pop queries.
- The Celery broker/backend URL is read from the `REDIS_URL` env var (defaulting to `redis://localhost:6379/0` for manual/local setups); under Docker Compose it's set to `redis://redis:6379/0` so the worker can reach the `redis` service by name.
- The client's Vite dev server is invoked directly (not via `npm run dev`) in Docker with `CI=true` set — this disables Vite's interactive stdin keypress-shortcut listener, which otherwise causes the dev server to exit as soon as it detects no interactive terminal attached.