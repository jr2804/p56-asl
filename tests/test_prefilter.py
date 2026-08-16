"""Tests for the P.56 protection pre-filter exposed via PyO3."""

from __future__ import annotations

import numpy as np
import pytest

from p56_asl import ActiveSpeechLevelMeter, PreFilter

pytest.importorskip("p56_asl._native", reason="native extension not built")


@pytest.mark.parametrize("band", ["NB", "nb", "Swb", "swb", "FB", "fb"])
def test_band_parse_case_insensitive(band: str) -> None:
    """Band names parse case-insensitively."""
    pf = PreFilter(band, 48_000)
    assert pf.band == band.lower()
    assert pf.sample_rate == 48_000.0


def test_band_parse_rejects_unknown() -> None:
    """Unknown band names raise ValueError."""
    with pytest.raises(ValueError, match="NB, SWB or FB"):
        PreFilter("MB", 48_000)


def test_invalid_sample_rate() -> None:
    """Rates below 4 kHz are rejected (narrowest corridor anchor)."""
    with pytest.raises(ValueError, match="sample rate"):
        PreFilter("NB", 3_000)


def test_process_returns_float32() -> None:
    """process() returns a new float32 array; input is not modified."""
    pf = PreFilter("NB", 16_000)
    x = np.zeros(1024, dtype=np.int16)
    out = pf.process(x)
    assert out.dtype == np.float32
    assert out.shape == (1024,)
    np.testing.assert_array_equal(x, np.zeros(1024, dtype=np.int16))


def test_streaming_matches_one_shot() -> None:
    """Chunked processing equals one-shot processing."""
    fs = 48_000.0
    t = np.arange(4_000, dtype=np.float64)
    x = (0.5 * np.sin(2 * np.pi * 800 * t / fs)).astype(np.float32)

    one = PreFilter("NB", fs)
    a = one.process(x)

    chunked = PreFilter("NB", fs)
    parts = [chunked.process(x[k : k + 37]) for k in range(0, len(x), 37)]
    b = np.concatenate(parts)

    np.testing.assert_allclose(a, b, atol=1e-6)


def test_dc_is_rejected() -> None:
    """A DC input decays to (near) zero through the high-pass cascade.

    The FB high-pass (24 Hz Butterworth-14) settles slowly (dominant pole
    ~60 ms), so a 5 s step is used and only the final second checked.
    """
    fs = 48_000
    for band in ("nb", "swb", "fb"):
        pf = PreFilter(band, fs)
        out = pf.process(np.ones(5 * fs, dtype=np.float32))
        assert np.abs(out[4 * fs :]).max() < 1e-4, band


def test_1khz_passband_flat() -> None:
    """Response at 1 kHz is 0 dB by construction; nearby in-band stays flat."""
    pf = PreFilter("NB", 48_000)
    assert pf.response_db(1_000) == pytest.approx(0.0, abs=1e-12)
    assert pf.response_db(500) == pytest.approx(0.0, abs=0.1)
    assert pf.response_db(3_000) == pytest.approx(0.0, abs=0.1)


def test_reset_clears_state() -> None:
    """After reset the impulse response restarts from zero state."""
    pf = PreFilter("NB", 16_000)
    x = (0.5 * np.sin(2 * np.pi * 300 * np.arange(2_000) / 16_000)).astype(np.float32)
    pf.process(x)
    pf.reset()
    out = pf.process(np.zeros(10, dtype=np.float32))
    np.testing.assert_array_equal(out, np.zeros(10, dtype=np.float32))


def test_prefilter_before_measurement() -> None:
    """Pre-filtering a signal then measuring shifts the ASL coherently."""
    fs = 16_000
    t = np.arange(fs * 2, dtype=np.float64)
    # Strong low-frequency hum + speech-band tone.
    x = (0.4 * np.sin(2 * np.pi * 50 * t / fs) + 0.2 * np.sin(2 * np.pi * 1000 * t / fs)).astype(np.float32)

    m_raw = ActiveSpeechLevelMeter(sample_rate=fs)
    m_raw.process_block(x)
    r_raw = m_raw.finish()

    pf = PreFilter("nb", fs)
    filtered = pf.process(x)
    m_pf = ActiveSpeechLevelMeter(sample_rate=fs)
    m_pf.process_block(filtered)
    r_pf = m_pf.finish()

    # The pre-filter removes the 50 Hz hum: ASL must drop by roughly the
    # hum's share of the total power (0.4^2 of 0.4^2+0.2^2 ≈ 6.0 dB).
    drop = r_raw.active_speech_level_db - r_pf.active_speech_level_db
    assert 3.0 < drop < 9.0
