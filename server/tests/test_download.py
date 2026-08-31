"""
Tests for methods/download.py
"""
from unittest.mock import patch, MagicMock

import pytest

from methods.download import download_track


def _mock_ydl_cm(mock_ydl_instance):
    """Build a MagicMock that behaves like the yt_dlp.YoutubeDL(...) context manager."""
    cm = MagicMock()
    cm.__enter__.return_value = mock_ydl_instance
    cm.__exit__.return_value = False
    return cm


def test_download_track_builds_expected_search_query():
    mock_ydl_instance = MagicMock()
    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)) as mock_cls:
        download_track("track1", "Song Name", "Artist Name")

    mock_ydl_instance.download.assert_called_once_with(["ytsearch1:Song Name Artist Name official audio"])
    # outtmpl should scope the download to this track's id
    opts_passed = mock_cls.call_args.args[0]
    assert opts_passed["outtmpl"] == "temp/track1.%(ext)s"


def test_download_track_skips_duration_check_when_not_provided():
    mock_ydl_instance = MagicMock()
    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)), \
         patch("methods.download.MP3") as mock_mp3:
        download_track("track1", "Song", "Artist")

    mock_mp3.assert_not_called()


def test_download_track_passes_when_duration_within_tolerance():
    mock_ydl_instance = MagicMock()
    mock_mp3_instance = MagicMock()
    mock_mp3_instance.info.length = 200  # seconds -> 200_000 ms
    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)), \
         patch("methods.download.MP3", return_value=mock_mp3_instance):
        # should not raise: actual (200_000ms) matches expected exactly
        download_track("track1", "Song", "Artist", expected_duration_ms=200_000)


def test_download_track_raises_when_actual_duration_too_long():
    mock_ydl_instance = MagicMock()
    mock_mp3_instance = MagicMock()
    mock_mp3_instance.info.length = 400  # 400_000ms actual vs 200_000ms expected -> ratio 2.0

    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)), \
         patch("methods.download.MP3", return_value=mock_mp3_instance):
        with pytest.raises(ValueError, match="Duration mismatch"):
            download_track("track1", "Song", "Artist", expected_duration_ms=200_000)


def test_download_track_raises_when_actual_duration_too_short():
    mock_ydl_instance = MagicMock()
    mock_mp3_instance = MagicMock()
    mock_mp3_instance.info.length = 50  # 50_000ms actual vs 200_000ms expected -> ratio 0.25

    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)), \
         patch("methods.download.MP3", return_value=mock_mp3_instance):
        with pytest.raises(ValueError, match="Duration mismatch"):
            download_track("track1", "Song", "Artist", expected_duration_ms=200_000)


def test_download_track_boundary_ratio_does_not_raise():
    # ratio of exactly 1.5 should NOT raise (condition is strictly > 1.5)
    mock_ydl_instance = MagicMock()
    mock_mp3_instance = MagicMock()
    mock_mp3_instance.info.length = 300  # 300_000ms actual vs 200_000ms expected -> ratio 1.5

    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)), \
         patch("methods.download.MP3", return_value=mock_mp3_instance):
        download_track("track1", "Song", "Artist", expected_duration_ms=200_000)

def test_download_track_does_not_use_unbounded_retries():
    """Regression guard: yt-dlp's own default (10) or an explicit None/unlimited
    retry count would reintroduce the unbounded-hang bug this config fixes."""
    mock_ydl_instance = MagicMock()
    with patch("methods.download.yt_dlp.YoutubeDL", return_value=_mock_ydl_cm(mock_ydl_instance)) as mock_cls:
        download_track("track1", "Song", "Artist")

    opts_passed = mock_cls.call_args.args[0]
    assert opts_passed.get("socket_timeout") is not None
    assert opts_passed.get("retries") not in (None, float("inf"))