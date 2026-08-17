"""Pytest configuration and fixtures for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import urllib.request
import zipfile
from pathlib import Path

import pytest
import soundfile as sf

from p56_asl import ActiveSpeechLevelMeter, PreFilter

P501_ANNEX_D_URL = "https://www.itu.int/wftp3/public/t/testsignal/GenAudio/P501/v2025_04/Speech_Signals_AnnexD.zip"

_test_dir = Path(__file__).parent


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Return the path to the test data directory."""
    return _test_dir / "data"


@pytest.fixture(scope="session")
def cache_subdir(request: pytest.FixtureRequest, subdir: str) -> Path:
    """Return a subdirectory in the pytest cache directory.

    Can be used by other fixtures to easily get a cache directory.
    """
    return Path(request.config.cache.mkdir(subdir))


@pytest.fixture(scope="session")
def p501_annex_d(request: pytest.FixtureRequest) -> list[Path]:
    """Download and extract the P.501 Annex D speech signals once per session.

    Returns the sorted list of extracted WAV files (cached under the
    pytest cache directory, so repeated runs skip the download).
    """
    cache = Path(request.config.cache.mkdir("p501-annex-d"))
    marker = cache / ".extracted"
    if not marker.is_file():
        zip_path = cache / "Speech_Signals_AnnexD.zip"
        urllib.request.urlretrieve(P501_ANNEX_D_URL, zip_path)  # noqa: S310
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(cache)
        zip_path.unlink()
        marker.touch()
    return sorted(cache.rglob("*.wav"))


def measure_wav(path: Path, band: str | None = None) -> tuple[float, float, int]:
    """Measure a WAV file through the same pipeline the CLI uses.

    Applies the P.56 pre-filter for `band` ("NB"/"SWB"/"FB" or `None`),
    returns `(active_speech_level_db, activity_factor, sample_rate)`.
    """
    frames, rate = sf.read(path, always_2d=True)
    samples = frames[:, 0].astype("float32", copy=False)
    rate = float(rate)
    if band is not None:
        prefilter = PreFilter(band, rate)
        prefilter.reset()
        samples = prefilter.process(samples)
    meter = ActiveSpeechLevelMeter(sample_rate=rate)
    for k in range(0, len(samples), 65536):
        meter.process_block(samples[k : k + 65536])
    result = meter.finish()
    return result.active_speech_level_db, result.activity_factor, int(rate)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: test downloads data from the internet (deselect with '-m \"not network\"')")
