import yt_dlp

def download_track(track_id, track_name, artist_name):
    query = f"{track_name} {artist_name} official audio"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'temp/{track_id}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"ytsearch1:{query}"])