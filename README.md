# PlaylistMatch

Find out which of your Spotify playlists a song *actually* fits — based on how it sounds, not just genre tags or metadata.

PlaylistMatch analyzes the raw audio of your Spotify playlists (chroma, timbre, spectral, and rhythm features) and lets you search for any song to see a similarity score against each of your playlists, plus the closest-matching tracks and new recommendations.

## How it works

1. **Connect Spotify** — the app authenticates via Spotify OAuth and pulls your accessible playlists.
2. **Ingest tracks** — each track is located on YouTube (via `yt-dlp`), downloaded as audio, and run through `librosa` to extract a feature vector: chroma STFT, MFCCs, spectral centroid, tempo, zero-crossing rate, and spectral rolloff. Vectors are cached in Pinecone so a track is only ever processed once.
3. **Search a song** — pick any track, and its feature vector is compared against every ingested playlist using a weighted, z-scored cosine similarity. Each playlist gets a match score, a top-5 breakdown, and "you might also like" recommendations pulled from the wider Pinecone index.

Playlist ingestion happens asynchronously via Celery so the UI can show live progress while tracks download and process in the background.

## Tech stack

**Backend**
- FastAPI — REST API
- Celery + Redis — background playlist ingestion
- Spotipy — Spotify Web API / OAuth
- yt-dlp + mutagen — locating and downloading audio
- librosa + numpy — audio feature extraction and similarity scoring
- Pinecone — vector storage and similarity search

**Frontend**
- React 19 + Vite
- React Router

## Project structure

```
server/
  api.py                  FastAPI app: auth, playlists, search endpoints
  celery_app.py           Celery app configuration
  tasks.py                Celery task definitions
  methods/
    playlists.py          Playlist ingestion + recommendations
    similarity.py          Feature scoring, means/stds/weights, query vectors
    metrics.py             librosa feature extraction (ingest_song)
    download.py             yt-dlp track downloading
    database.py             Pinecone read/write helpers
  evals/                   Offline rap-vs-pop separation evaluation
  tests/                   pytest suite

client/
  src/
    pages/                 Login and Home pages
    styles/                Page styles
  vite.config.js
```

## Getting started

### Prerequisites

- Python 3.12
- Node.js
- Redis (for Celery broker/backend)
- A [Spotify Developer](https://developer.spotify.com/dashboard) app (client ID/secret + redirect URI)
- A [Pinecone](https://www.pinecone.io/) account and index named `chromavec`
- `ffmpeg` installed and on your `PATH` (required by `yt-dlp`/`mutagen` for audio extraction)

### Backend setup

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

### Frontend setup

```bash
cd client
npm install
npm run dev
```

Visit the client (default `http://localhost:5173`), connect your Spotify account, and search for a song once your playlists finish processing.

### Running tests

```bash
cd server
pytest tests/ --ignore=tests/test_eval_script.py -v --cov=methods --cov-report=term-missing
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
| `GET /playlists` | Lists the user's accessible playlists and kicks off async ingestion jobs |
| `GET /playlists/status/{job_id}` | Polls ingestion job status |
| `GET /track-search?q=` | Autocomplete search for a track via Spotify |
| `POST /search` | Scores a track against one or more ingested playlists |

## Notes

- Audio is downloaded temporarily to `server/temp/` and deleted immediately after feature extraction.
- Similarity scoring z-scores each feature against FMA dataset baselines (`methods/similarity.py`), clips outliers, and applies per-feature weights before computing cosine similarity — this keeps high-variance features like MFCCs from dominating the score.
- `server/evals/` contains a standalone script for sanity-checking that rap reference tracks score meaningfully higher against rap queries than pop queries.