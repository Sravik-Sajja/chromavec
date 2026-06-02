from methods.metrics import ingest_song
from methods.download import download_track
from methods.database import fetch_similarities
import os

def get_playlist_similarity(track_id, track_name, artist_name):
    file_path = f"temp/{track_id}.mp3"
    download_track(track_id, track_name, artist_name)
    vector = ingest_song(track_id)
    print(f"Vector sample: {vector[:5]}")
    
    results = fetch_similarities(vector)
    for match in results.matches:
        print(match.id, match.values)
    
    for match in results.matches:
        print(f"{match.metadata.get('name')} by {match.metadata.get('artist')}: {match.score:.2f}")
    
    if os.path.exists(file_path):
        os.remove(file_path)

if __name__ == "__main__":
    '''track_id1 = "2IRZnDFmlqMuOrYOLnZZyc"
    track_name1 = "Going Bad(feat. Drake)"
    artist_name1 = "Meek Mill"
    
    get_playlist_similarity(track_id1, track_name1, artist_name1)
    '''

    track_id = "53iuhJlwXhSER5J2IYYv1W"
    track_name = "The Fate of Ophelia"
    artist_name = "Taylor Swift"
    
    get_playlist_similarity(track_id, track_name, artist_name)
