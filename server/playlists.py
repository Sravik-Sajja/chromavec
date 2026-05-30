import spotipy
import yt_dlp

def process_playlists(sp, playlists):
    for playlist in playlists['items']:
        try:
            all_tracks = sp.playlist_tracks(playlist['id'])
            process_tracks(all_tracks)
        except Exception as e:
            print(f"Skipping {playlist['name']}: {e}")
            continue

def process_tracks(all_tracks):
    for item in all_tracks['items']:
        track = item.get('item')
        if not track:
            continue
        
        track_name = track['name']
        artist_name = track['artists'][0]['name']
        query = f"{track_name} {artist_name} official audio"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'temp/{track["id"]}.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])

if __name__ == "__main__":
    process_tracks({
        'items': [
            {
                'item': {
                    'id': '4uLU6hMCjMI75M1A2tKUQC',
                    'name': 'Baby',
                    'artists': [{'name': 'Lil Baby'}]
                }
            }
        ]
    })