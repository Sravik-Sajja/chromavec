import librosa
import numpy as np

def ingest_song(track_id):
    file_path = f"temp/{track_id}.mp3"
    
    y, sr = librosa.load(file_path, sr=11025)
    
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    zcr = librosa.feature.zero_crossing_rate(y)
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    
    vector = np.concatenate([
        chroma.mean(axis=1),
        mfcc.mean(axis=1),
        [centroid.mean()],
        [tempo],
        [zcr.mean()],
        [rolloff.mean()]
    ])
    return vector.tolist()