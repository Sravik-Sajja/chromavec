from methods.metrics import ingest_song
from methods.download import download_track
from methods.database import fetch_similarities
import numpy as np
import os

#MEANS and STDS taken from fma average
MEANS = np.array([
    0.4560, 0.4431, 0.4589, 0.4460, 0.4606, 0.4420,
    0.4330, 0.4477, 0.4412, 0.4573, 0.4393, 0.4536,
    -211.6422, 146.6749, -11.7791, 27.2229, 2.8596, 12.8215,
    -2.6106, 5.5534, -1.6659, 1.8904, -2.0632, 0.9773,
    -1.8176, 0.1543, -1.5661, -0.6526, -1.7717, -0.8725,
    -1.2208, -1.2285,
    1177.6213, 120.0, 0.0528, 2356.1193
])

STDS = np.array([
    0.1297, 0.1242, 0.1282, 0.1260, 0.1300, 0.1288,
    0.1215, 0.1220, 0.1201, 0.1243, 0.1203, 0.1236,
    98.8998, 34.9541, 31.1909, 20.1126, 13.6342, 11.9429,
    9.8629, 9.1615, 7.1715, 7.7791, 6.1713, 6.3247,
    5.3574, 5.5506, 4.8190, 4.9088, 4.4388, 4.6032,
    4.0396, 4.2172,
    530.8179, 35.0, 0.0326, 1145.0514
])

WEIGHTS = np.array(
    [0.6] * 12 +   # chroma
    [0.7] +        # mfcc[0]
    [0.3] +        # mfcc[1]
    [1.5] * 18 +   # mfcc[2-19]
    [1.0] +        # centroid
    [1.8] +        # tempo
    [0.1] +        # zcr
    [0.6]          # rolloff
)

def weighted_cosine(v1, v2):
    z1 = np.clip((np.array(v1) - MEANS) / STDS, -3, 3) * WEIGHTS
    z2 = np.clip((np.array(v2) - MEANS) / STDS, -3, 3) * WEIGHTS
    denom = np.linalg.norm(z1) * np.linalg.norm(z2)
    if denom == 0:
        return 0.0
    return float(np.dot(z1, z2) / denom)

def get_playlist_similarity(track_id, track_name, artist_name):
    file_path = f"temp/{track_id}.mp3"
    download_track(track_id, track_name, artist_name)
    query_vector = np.array(ingest_song(track_id))

    results = fetch_similarities(query_vector.tolist())

    scored = []
    for match in results.matches:
        stored = np.array(match.values)
        score = weighted_cosine(query_vector, stored)
        scored.append((score, match.metadata))

    scored.sort(reverse=True)

    print(f"\nResults for: {track_name} by {artist_name}")
    for score, meta in scored:
        print(f"  {meta.get('name')} by {meta.get('artist')}: {score:.4f}")

    if os.path.exists(file_path):
        os.remove(file_path)
