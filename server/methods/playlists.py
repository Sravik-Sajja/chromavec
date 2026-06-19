import spotipy
from methods.metrics import ingest_song
from methods.database import upsert_batch_of_tracks, fetch_already_ingested
from methods.download import download_track
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import signal

def process_playlists(sp, playlists):
    for playlist in playlists['items']:
        try:
            # collect all track ids in playlist
            all_tracks = sp.playlist_tracks(playlist['id'])
            track_ids = []
            track_map = {}

            while all_tracks:
                for item in all_tracks['items']:
                    track = item.get('item')
                    if not track:
                        continue
                    track_ids.append(track['id'])
                    track_map[track['id']] = track
                
                # fetch next page if it exists
                all_tracks = sp.next(all_tracks) if all_tracks['next'] else None
            
            # batch check against pinecone
            already_ingested = fetch_already_ingested(track_ids)

            playlist['track_ids'] = track_ids

            # only process new tracks
            new_tracks = [track_map[tid] for tid in track_ids if tid not in already_ingested]
            print(f"{playlist['name']}: {len(already_ingested)} cached, {len(new_tracks)} new")
            
            total_ingested = process_tracks(new_tracks)
            playlist['total_ingested'] = total_ingested + len(already_ingested)
        except Exception as e:
            print(f"Skipping {playlist['name']}: {e}")
            playlist['track_ids'] = []
            playlist['total_ingested'] = 0
            continue
    return playlists

def process_tracks(tracks):
    results = []
    total_ingested = 0

    with ProcessPoolExecutor(max_workers=4) as executor:
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
        print(f"Ingested {total_ingested} tracks")
        upsert_batch_of_tracks(results)
    
    return total_ingested

def process_one(track):
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Timed out on {track['name']}")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(15)
    
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