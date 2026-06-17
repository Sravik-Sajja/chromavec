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

def fetch_similarities(vector):
    results = index.query(
        vector=vector,
        top_k=100,
        include_metadata=True,
        include_values=True
    )
    return results