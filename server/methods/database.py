from pinecone import Pinecone
import os
from dotenv import load_dotenv

load_dotenv()


class _LazyIndex:
    """Defers Pinecone client/index creation until first use, so importing
    this module doesn't require credentials or network access."""

    def __init__(self):
        self._index = None

    def _ensure(self):
        if self._index is None:
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            self._index = pc.Index("chromavec")
        return self._index

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


index = _LazyIndex()


def reset_index():
    """Recreate the lazy client — used after forking a new celery worker."""
    global index
    index = _LazyIndex()


def upsert_track(track_id, vector, metadata):
    try:
        return index.upsert(vectors=[
            {"id": track_id, "values": vector, "metadata": metadata}
        ])
    except Exception as e:
        print(f"[upsert_track] Failed: {e}")
        return None


def upsert_batch_of_tracks(records):
    try:
        return index.upsert(vectors=[
            {"id": track_id, "values": vector, "metadata": metadata}
            for track_id, vector, metadata in records
        ])
    except Exception as e:
        print(f"[upsert_batch_of_tracks] Failed upload: {e}")
        return None


def fetch_already_ingested(track_ids):
    try:
        if not track_ids:
            return set()
        result = index.fetch(ids=track_ids)
        return set(result.vectors.keys())
    except Exception as e:
        print(f"[fetch_already_ingested] Failed: {e}")
        return set()


def fetch_vectors_for_ids(track_ids):
    try:
        if not track_ids:
            return {}
        all_vectors = {}
        chunk_size = 1000
        for i in range(0, len(track_ids), chunk_size):
            chunk = track_ids[i:i + chunk_size]
            try:
                result = index.fetch(ids=chunk)
                for tid, vec_obj in result.vectors.items():
                    all_vectors[tid] = {
                        "values": vec_obj.values,
                        "metadata": vec_obj.metadata,
                    }
            except Exception as e:
                print(f"[fetch_vectors_for_ids] Chunk failed ({i}-{i+chunk_size}): {e}")
                continue
        return all_vectors
    except Exception as e:
        print(f"[fetch_vectors_for_ids] Failed: {e}")
        return {}


def query_similar(vector, top_k=50):
    try:
        result = index.query(vector=vector, top_k=top_k, include_metadata=True)
        return result.matches
    except Exception as e:
        print(f"[query_similar] Failed: {e}")
        return []