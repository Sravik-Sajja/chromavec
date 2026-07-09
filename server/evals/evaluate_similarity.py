"""
similarity evaluation
Compares 10 rap + 10 pop query songs against 20 rap reference vectors.
Prints per-song scores, group averages, and a separation summary.
Reingests every song if not in local cache
"""

import numpy as np
from methods.download import download_track
from methods.metrics import ingest_song
from methods.similarity import MEANS, STDS, WEIGHTS, weighted_cosine
from evals.data import RAP_REFERENCE, RAP_QUERIES, POP_QUERIES
import os


def get_vector(track):
    """Download, extract vector, clean up."""
    tid = track["id"]
    path = f"temp/{tid}.mp3"
    try:
        print(f"  → downloading {track['name']} by {track['artist']} ...", flush=True)
        download_track(tid, track["name"], track["artist"])
        return ingest_song(tid)
    finally:
        if os.path.exists(path):
            os.remove(path)

# ── fetch reference vectors (local cache, no Pinecone needed) ─────────────────

CACHE_FILE = "temp/test_vectors.npy"

def fetch_reference_vectors(tracks):
    """Vectorize reference tracks, cache to disk so re-runs are instant."""
    # load existing cache
    if os.path.exists(CACHE_FILE):
        cached = dict(np.load(CACHE_FILE, allow_pickle=True).item())
    else:
        cached = {}

    vectors = {}
    newly_computed = {}

    for track in tracks:
        tid = track["id"]
        if tid in cached:
            print(f"  ✓ cached  {track['name']}")
            vectors[tid] = cached[tid]
        else:
            try:
                vec = get_vector(track)
                vectors[tid] = vec
                newly_computed[tid] = vec
            except Exception as e:
                print(f"  ✗ failed  {track['name']}: {e}")

    # save updated cache
    if newly_computed:
        cached.update(newly_computed)
        os.makedirs("temp", exist_ok=True)
        np.save(CACHE_FILE, cached)
        print(f"  → cached {len(newly_computed)} new vectors to {CACHE_FILE}")

    return vectors

# ── scoring ────────────────────────────────────────────────────────────────────

def score_against_reference(query_vector, ref_vectors):
    """Return list of (score, track_id) sorted descending."""
    scores = [(weighted_cosine(query_vector, v), tid) for tid, v in ref_vectors.items()]
    return sorted(scores, reverse=True)

def run_test(label, queries, ref_vectors, ref_tracks):
    id_to_name = {t["id"]: f"{t['name']} — {t['artist']}" for t in ref_tracks}
    group_scores = []

    cached = dict(np.load(CACHE_FILE, allow_pickle=True).item()) if os.path.exists(CACHE_FILE) else {}

    print(f"\n{'═'*64}")
    print(f"  {label}  ({len(queries)} songs vs {len(ref_vectors)} rap references)")
    print(f"{'═'*64}")

    for track in queries:
        print(f"\n▶ {track['name']} by {track['artist']}")
        try:
            if track["id"] in cached:
                print(f"  ✓ cached")
                vec = cached[track["id"]]
            else:
                vec = get_vector(track)
                cached[track["id"]] = vec
                np.save(CACHE_FILE, cached)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        scores = score_against_reference(vec, ref_vectors)
        top5 = scores[:5]
        avg = np.mean([s for s, _ in scores])
        group_scores.append(avg)

        print(f"  avg similarity to rap refs : {avg:.4f}")
        print(f"  top 5 matches:")
        for rank, (score, tid) in enumerate(top5, 1):
            print(f"    {rank}. {id_to_name.get(tid, tid):<45} {score:.4f}")

    return group_scores

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print("\nFetching reference vectors...")
    ref_vectors = fetch_reference_vectors(RAP_REFERENCE)
    if not ref_vectors:
        print("No reference vectors found. Make sure RAP_REFERENCE tracks are ingested.")
        return

    rap_scores  = run_test("RAP QUERIES",  RAP_QUERIES,  ref_vectors, RAP_REFERENCE)
    pop_scores  = run_test("POP QUERIES",  POP_QUERIES,  ref_vectors, RAP_REFERENCE)

    # ── separation summary ─────────────────────────────────────────────────────
    print(f"\n{'═'*64}")
    print("  SEPARATION SUMMARY")
    print(f"{'═'*64}")
    if rap_scores:
        print(f"  rap avg  : {np.mean(rap_scores):.4f}  "
              f"(min {np.min(rap_scores):.4f} / max {np.max(rap_scores):.4f})")
    if pop_scores:
        print(f"  pop avg  : {np.mean(pop_scores):.4f}  "
              f"(min {np.min(pop_scores):.4f} / max {np.max(pop_scores):.4f})")
    if rap_scores and pop_scores:
        gap = np.mean(rap_scores) - np.mean(pop_scores)
        print(f"  gap      : {gap:+.4f}")
    print()

if __name__ == "__main__":
    main()