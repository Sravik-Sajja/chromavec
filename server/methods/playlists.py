import spotipy
from methods.metrics import ingest_song
from methods.database import upsert_batch_of_tracks, fetch_already_ingested, fetch_vectors_for_ids, query_similar
from methods.download import download_track
from methods.similarity import weighted_cosine
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import signal
import numpy as np
import time
from methods.locks import redis_client

_FORK_CTX = mp.get_context("fork")


def process_single_playlist(playlist_id, track_ids, serializable_tracks):
    # batch check against pinecone
    already_ingested = fetch_already_ingested(track_ids)
    # only process new tracks
    new_tracks = [t for t in serializable_tracks if t['id'] not in already_ingested]
    print(f"playlist {playlist_id}: {len(already_ingested)} cached, {len(new_tracks)} new")

    total_ingested = process_tracks(new_tracks) + len(already_ingested)

    try:
        recommendations = get_playlist_recommendations(track_ids)
    except Exception as e:
        print(f"Skipping recommendations for {playlist_id}: {e}")
        recommendations = []

    return {
        "total_ingested": total_ingested,
        "recommendations": recommendations,
        "track_ids": track_ids,
    }


def get_playlist_recommendations(track_ids):
    if not track_ids:
        return []

    vectors = fetch_vectors_for_ids(track_ids)
    if not vectors:
        return []

    track_id_set = set(track_ids)
    avg_vector = np.array([v["values"] for v in vectors.values()]).mean(axis=0).tolist()

    top_k = min(len(track_ids) + 40, 1000)
    matches = query_similar(avg_vector, top_k=top_k)

    candidate_ids = [m.id for m in matches if m.id not in track_id_set]
    candidate_vectors = fetch_vectors_for_ids(candidate_ids)

    scored = [
        (weighted_cosine(avg_vector, v["values"]), tid, v["metadata"])
        for tid, v in candidate_vectors.items()
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": tid,
            "name": meta.get("name"),
            "artist": meta.get("artist"),
            "score": round(score * 100, 1),
        }
        for score, tid, meta in scored[:3]
    ]

def process_tracks(tracks):
    results = []
    total_ingested = 0

    with ProcessPoolExecutor(max_workers=4, mp_context=_FORK_CTX) as executor:
        futures = {executor.submit(process_one, t): t for t in tracks}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
                    if len(results) >= 100:
                        total_ingested += len(results)
                        upsert_batch_of_tracks(results.copy())
                        results.clear()
            except Exception as e:
                track = futures[future]
                print(f"  Unhandled error for {track['name']}: {e}")

    if results:
        total_ingested += len(results)
        if upsert_batch_of_tracks(results):
            print(f"Ingested {total_ingested} tracks")

    return total_ingested

LOCK_WAIT_SECONDS = 40
LOCK_POLL_INTERVAL = 8

def process_one(track):
    track_id = track["id"]
    lock = redis_client.lock(f"ingest:{track_id}", timeout=60)

    if not lock.acquire(blocking=False):
        # someone else is already downloading this exact track
        return _wait_for_sibling(track_id)

    try:
        return _download_and_ingest(track)
    finally:
        lock.release()


def _wait_for_sibling(track_id):
    waited = 0
    while waited < LOCK_WAIT_SECONDS:
        time.sleep(LOCK_POLL_INTERVAL)
        waited += LOCK_POLL_INTERVAL
        if fetch_vectors_for_ids([track_id]):
            return None  # sibling finished
    return None  # gave up waiting


def _download_and_ingest(track):
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Timed out on {track['name']}")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(40)

    track_id = track["id"]
    file_path = f"temp/{track_id}.mp3"
    print(track["name"])

    try:
        download_track(track_id, track['name'], track['artist'], track.get('duration_ms'))
        vector_data = ingest_song(track_id)
        metadata = {
            "name": str(track.get("name") or ""),
            "artist": str(track.get("artist") or ""),
            "album": str(track.get("album") or ""),
            "duration_ms": int(track.get("duration_ms") or 0),
        }
        return (track_id, vector_data, metadata)
    except TimeoutError:
        print(f"  Timed out, skipping {track['name']}")
        return None
    except Exception as e:
        print(f"  Failed {track['name']}: {e}")
        return None
    finally:
        signal.alarm(0)
        if os.path.exists(file_path):
            os.remove(file_path)