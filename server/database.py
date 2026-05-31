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

def track_already_ingested(track_id):
    result = index.fetch(ids=[track_id])
    if result: return True
    else: return False