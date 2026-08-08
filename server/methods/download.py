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
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
    except Exception as e:
        print(f"[download] yt-dlp failed for '{track_name}' by {artist_name} (id={track_id}): {type(e).__name__}: {e}")
        raise

    if expected_duration_ms:
        file_path = f"temp/{track_id}.mp3"
        try:
            actual_ms = MP3(file_path).info.length * 1000
        except Exception as e:
            print(f"[duration_check] couldn't read mp3 for '{track_name}' (id={track_id}) at {file_path}: {type(e).__name__}: {e}")
            raise

        ratio = actual_ms / expected_duration_ms
        if ratio > 1.5 or ratio < 0.5:
            raise ValueError(
                f"Duration mismatch for {track_name}: "
                f"expected {expected_duration_ms/1000:.0f}s got {actual_ms/1000:.0f}s"
            )