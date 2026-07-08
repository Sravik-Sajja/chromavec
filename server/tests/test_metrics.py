"""
Tests for methods/metrics.py
Output vector in order and expected values is assumed
"""
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from methods.metrics import ingest_song


def _make_feature(rows, cols, value):
    return np.full((rows, cols), value, dtype=float)


class _LibrosaMocks:
    """Patches every librosa call ingest_song makes and keeps direct
    references to each mock so assertions work after the `with` block."""

    def __init__(self, chroma_val=0.5, mfcc_val=2.0, centroid_val=1000.0,
                 tempo_val=120.0, zcr_val=0.05, rolloff_val=3000.0,
                 tempo_as_array=True):
        self.load = MagicMock(return_value=(np.zeros(1000), 11025))
        self.chroma_stft = MagicMock(return_value=_make_feature(12, 5, chroma_val))
        self.mfcc = MagicMock(return_value=_make_feature(20, 5, mfcc_val))
        self.spectral_centroid = MagicMock(return_value=_make_feature(1, 5, centroid_val))
        self.zero_crossing_rate = MagicMock(return_value=_make_feature(1, 5, zcr_val))
        self.spectral_rolloff = MagicMock(return_value=_make_feature(1, 5, rolloff_val))

        tempo_return = np.array([tempo_val]) if tempo_as_array else tempo_val
        self.beat_track = MagicMock(return_value=(tempo_return, np.array([1, 2, 3])))

    def __enter__(self):
        self._stack = ExitStack()
        self._stack.enter_context(patch("methods.metrics.librosa.load", self.load))
        self._stack.enter_context(patch("methods.metrics.librosa.feature.chroma_stft", self.chroma_stft))
        self._stack.enter_context(patch("methods.metrics.librosa.feature.mfcc", self.mfcc))
        self._stack.enter_context(patch("methods.metrics.librosa.feature.spectral_centroid", self.spectral_centroid))
        self._stack.enter_context(patch("methods.metrics.librosa.feature.zero_crossing_rate", self.zero_crossing_rate))
        self._stack.enter_context(patch("methods.metrics.librosa.feature.spectral_rolloff", self.spectral_rolloff))
        self._stack.enter_context(patch("methods.metrics.librosa.beat.beat_track", self.beat_track))
        return self

    def __exit__(self, *exc_info):
        self._stack.close()
        return False


def test_ingest_song_returns_vector_of_length_36():
    with _LibrosaMocks():
        vector = ingest_song("track1")

    assert len(vector) == 36


def test_ingest_song_feature_order_is_chroma_mfcc_centroid_tempo_zcr_rolloff():
    with _LibrosaMocks(
        chroma_val=0.1, mfcc_val=0.2, centroid_val=0.3,
        tempo_val=0.4, zcr_val=0.5, rolloff_val=0.6,
    ):
        vector = ingest_song("track1")

    assert vector[0:12] == pytest.approx([0.1] * 12)
    assert vector[12:32] == pytest.approx([0.2] * 20)
    assert vector[32] == pytest.approx(0.3)
    assert vector[33] == pytest.approx(0.4)
    assert vector[34] == pytest.approx(0.5)
    assert vector[35] == pytest.approx(0.6)


def test_ingest_song_loads_file_at_expected_path_and_sample_rate():
    with _LibrosaMocks() as mocks:
        ingest_song("abc123")

    args, kwargs = mocks.load.call_args
    assert args[0] == "temp/abc123.mp3"
    assert kwargs["sr"] == 11025


def test_ingest_song_handles_scalar_tempo_not_just_array():
    with _LibrosaMocks(tempo_val=98.6, tempo_as_array=False):
        vector = ingest_song("track1")

    assert vector[33] == pytest.approx(98.6)


def test_ingest_song_returns_plain_python_list():
    with _LibrosaMocks():
        vector = ingest_song("track1")

    assert isinstance(vector, list)
    assert all(isinstance(x, float) for x in vector)