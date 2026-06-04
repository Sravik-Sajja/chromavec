'''
Use fma data set to get baseline means and std for each data point
'''
from pathlib import Path
import pandas as pd
import numpy as np

csv_path = Path(__file__).parent / "features.csv"
def get_avgs():
    # read in chunks so it doesn't freeze
    chunks = []
    for chunk in pd.read_csv(csv_path, chunksize=1000, header=[0,1,2], index_col=0):
        chunks.append(chunk)
        print(f"loaded {len(chunks)*1000} rows...")

    df = pd.concat(chunks)
    # see all unique feature types
    # extract the 'mean' statistic for each feature
    chroma_stft_mean = df['chroma_stft']['mean']        # 12 cols
    mfcc_mean = df['mfcc']['mean']                      # 20 cols
    centroid_mean = df['spectral_centroid']['mean']      # 1 col
    zcr_mean = df['zcr']['mean']                        # 1 col
    rolloff_mean = df['spectral_rolloff']['mean']        # 1 col

    # we don't have tempo in FMA features so skip for now

    # compute across all 106k songs
    print("chroma_stft mean:", chroma_stft_mean.mean().values)
    print("chroma_stft std:", chroma_stft_mean.std().values)
    print()
    print("mfcc mean:", mfcc_mean.mean().values)
    print("mfcc std:", mfcc_mean.std().values)
    print()
    print("centroid mean:", centroid_mean.mean().values)
    print("centroid std:", centroid_mean.std().values)
    print()
    print("zcr mean:", zcr_mean.mean().values)
    print("zcr std:", zcr_mean.std().values)
    print()
    print("rolloff mean:", rolloff_mean.mean().values)
    print("rolloff std:", rolloff_mean.std().values)

if __name__ == "__main__":
    get_avgs()