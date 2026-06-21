from pinecone import Pinecone
import os
from dotenv import load_dotenv

load_dotenv()
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("chromavec")

def upsert_track(track_id, vector, metadata):
    index.upsert(vectors=[
        {
            "id": track_id,
            "values": vector,
            "metadata": metadata
        }
    ])

def upsert_batch_of_tracks(records):
    index.upsert(vectors=[
        {
            "id": track_id,
            "values": vector,
            "metadata": metadata
        }
        for track_id, vector, metadata in records
    ])

def fetch_already_ingested(track_ids):
    result = index.fetch(ids=track_ids)
    already_ingested = set(result.vectors.keys())
    return already_ingested


def fetch_vectors_for_ids(track_ids):
    if not track_ids:
        return {}
 
    all_vectors = {}
    chunk_size = 1000
    for i in range(0, len(track_ids), chunk_size):
        chunk = track_ids[i:i + chunk_size]
        result = index.fetch(ids=chunk)
        for tid, vec_obj in result.vectors.items():
            all_vectors[tid] = {
                "values": vec_obj.values,
                "metadata": vec_obj.metadata,
            }
    return all_vectors

def query_similar(vector, top_k=50):
    result = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True
    )
    return result.matches