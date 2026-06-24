import yt_dlp
from mutagen.mp3 import MP3

def download_track(track_id, track_name, artist_name, expected_duration_ms=None):
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

    if expected_duration_ms:
        file_path = f"temp/{track_id}.mp3"
        actual_ms = MP3(file_path).info.length * 1000
        ratio = actual_ms / expected_duration_ms
        if ratio > 1.5 or ratio < 0.5:
            raise ValueError(
                f"Duration mismatch for {track_name}: "
                f"expected {expected_duration_ms/1000:.0f}s got {actual_ms/1000:.0f}s"
            )