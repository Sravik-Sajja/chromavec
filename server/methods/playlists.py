import spotipy
from methods.metrics import ingest_song
from methods.database import upsert_track, fetch_already_ingested
from methods.download import download_track
import os

def process_playlists(sp, playlists):
    for playlist in playlists['items']:
        try:
            all_tracks = sp.playlist_tracks(playlist['id'])
            
            # collect all track ids in playlist
            track_ids = []
            track_map = {}
            for item in all_tracks['items']:
                track = item.get('item')
                if not track:
                    continue
                track_ids.append(track['id'])
                track_map[track['id']] = track
            
            # batch check against pinecone
            already_ingested = fetch_already_ingested(track_ids)
            
            # only process new tracks
            new_tracks = [track_map[tid] for tid in track_ids if tid not in already_ingested]
            print(f"{playlist['name']}: {len(already_ingested)} cached, {len(new_tracks)} new")
            
            process_tracks(new_tracks)
        except Exception as e:
            print(f"Skipping {playlist['name']}: {e}")
            if(playlist['name'] == "Oldies"): break
            continue
        if(playlist['name'] == "Oldies"): break

def process_tracks(tracks):
    for track in tracks:
        track_id = track["id"]
        file_path = f"temp/{track_id}.mp3"
        print(track["name"])
        
        try:
            download_track(track_id, track['name'], track['artists'][0]['name'])
            
            vector_data = ingest_song(track_id)
            metadata = {
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "album": track["album"]["name"],
                "duration_ms": track["duration_ms"],
            }
            #upsert_track(track_id, vector_data, metadata)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

if __name__ == "__main__":
    process_tracks([
        {
            'id': '4uLU6hMCjMI75M1A2tKUQC',
            'name': 'Baby',
            'artists': [{'name': 'Lil Baby'}],
            'album': {'name': 'My Turn'},
            'duration_ms': 180000
        },
        {
            'id': '7uLU6hMCjMI75M1A2tKUQC',
            'name': 'Too Comfortable',
            'artists': [{'name': 'Future'}],
            'album': {'name': 'DS2'},
            'duration_ms': 210000
        }
    ])