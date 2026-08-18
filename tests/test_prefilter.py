"""Tests for the P.56 protection pre-filter exposed via PyO3."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xy.pyplot as plt

from p56_asl import ActiveSpeechLevelMeter, PreFilter


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
    x = np.zeros(1024, dtype=np.float32)
    out = pf.process(x)
    assert out.dtype == np.float32
    assert out.shape == (1024,)
    np.testing.assert_array_equal(x, np.zeros(1024, dtype=np.float32))


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


def test_plot_response_and_tolerance_corridor() -> None:
    """Render response vs ITU tolerance corridor for NB, SWB, FB to tests/plots/.

    Single figure, three panels (one per band), log-frequency axis. The
    corridor anchors are ITU-T Rec. P.56 Tables 3 / B.1 / C.1; the upper
    limit interpolates linearly in log10(f) between anchors and clamps
    outside, the lower limit is a flat -0.25 dB segment. The plot doubles
    as a verification: every band must stay inside its corridor on the
    plotted grid.
    """
    # Operating rate of the suite/reference implementation; the spec's
    # 70 kHz corridor anchors just mean "up to the upper end" and are
    # evaluated up to Nyquist (24 kHz) here.
    fs = 48_000.0
    bands = ("NB", "SWB", "FB")
    corridor: dict[str, tuple[list[tuple[float, float]], list[tuple[float, float]]]] = {
        "NB": ([(16.0, -49.75), (160.0, 0.25), (7000.0, 0.25), (70000.0, -49.75)], [(200.0, -0.25), (5500.0, -0.25)]),
        "SWB": ([(16.0, -49.75), (50.0, 0.25), (14000.0, 0.25), (70000.0, -49.75)], [(70.0, -0.25), (12000.0, -0.25)]),
        "FB": ([(9.0, -49.75), (20.0, 0.25), (20000.0, 0.25), (70000.0, -49.75)], [(30.0, -0.25), (18000.0, -0.25)]),
    }

    f = np.logspace(np.log10(5.0), np.log10(fs / 2), 2_000)

    def upper_db(anchors: list[tuple[float, float]]) -> np.ndarray:
        fa = np.array([a[0] for a in anchors])
        la = np.array([a[1] for a in anchors])
        return np.interp(np.log10(f), np.log10(fa), la, left=la[0], right=la[-1])

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True, constrained_layout=True)
    # Okabe-Ito palette (colorblind-safe); solid vs dashed adds redundant
    # encoding beyond hue. No suptitle — the docstring is the caption.
    c_resp, c_limit = "#0072B2", "#D55E00"
    for letter, ax, band in zip("ABC", axes, bands, strict=False):
        up = upper_db(corridor[band][0])
        lo = np.full_like(f, np.nan)
        (f0, lo_db), (f1, _) = corridor[band][1]
        lo[(f >= f0) & (f <= f1)] = lo_db

        resp = np.array([PreFilter(band, fs).response_db(fi) for fi in f])

        ax.plot(f, resp, color=c_resp, lw=1.5, label="response")
        ax.plot(f, up, "--", color=c_limit, lw=1.5, label="upper limit")
        # Lower limit is a finite segment only (flat -0.25 dB); plotting it
        # as a masked slice keeps the dash style (NaN gaps render solid).
        fin = np.isfinite(lo)
        ax.plot(f[fin], lo[fin], "--", color=c_limit, lw=1.5, label="lower limit")
        ax.axvline(1_000, color="gray", lw=0.8, ls=":")
        ax.set_title(f"{letter} — {band}", loc="left", fontweight="bold", fontsize=12)
        ax.set_xlabel("frequency [Hz]", fontsize=12)
        ax.tick_params(labelsize=10)
        # xy's semilogx() renders no x ticks; set the log scale explicitly.
        ax.set_xscale("log")
        ax.set_xticks([10, 100, 1_000, 10_000])
        ax.set_xlim(5.0, fs / 2)
        ax.set_ylim(-25.0, 5.0)
        ax.grid(which="both", alpha=0.3)

        # Verification on the plotted grid: response stays inside corridor.
        viol = np.nanmax(np.maximum(resp - up, lo - resp))
        assert viol <= 0.05, f"{band} violates corridor by {viol:.3f} dB"

    axes[0].set_ylabel("relative response [dB]", fontsize=12)
    axes[0].legend(fontsize=10, frameon=False)

    out = Path(__file__).parent / "plots" / "prefilter_response.svg"
    out.parent.mkdir(exist_ok=True)
    plt.savefig(out)
    plt.close(fig)
    assert out.stat().st_size > 0
