"""Integration tests against ITU-T P.501 Annex D speech signals.

The P.501 Annex D corpus (2025-04) contains speech signals whose active
speech level is normalized to −26.0 dBov. Filename suffixes encode the
bandwidth (`_NB`, `_SWB`, `_FB`) which selects the matching P.56
pre-filter (clause 10.2 / Annex B / Annex C).

Downloads are cached in the pytest cache directory (`tests/test-cache`);
deselect with `-m "not network"` when offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from p56_asl import ActiveSpeechLevelMeter, PreFilter
from p56_asl.cli.app import app

from .conftest import measure_wav

EXPECTED_ASL_DB = -26.0
#: Empirical corpus tolerance. The Annex D corpus is *normalized* to
#: −26 dBov, but re-measuring it with P.56 shows intrinsic deviations:
#: the ITU reference C implementation (`ref/sv56demo`) reproduces the
#: same per-file deviations (max ±0.65 dB, e.g. P501_D_FI_fm_IRS_08k
#: measures −25.354 dBov with the reference) — quantization and edge
#: effects of the normalization round-trip. 0.7 dB covers the reference
#: spread with margin.
TOLERANCE_DB = 0.7
#: Scaling must be exactly linear: measuring the scaled signal and
#: subtracting the measured baseline cancels the corpus deviation, so a
#: tight bound applies (float32 + auto-calibration round-off only).
LINEARITY_TOLERANCE_DB = 0.10

_SCALE_OFFSETS_DB = [-60.0, -30.0, 30.0, 60.0]


_ = measure_wav  # re-exported for interactive debugging; keep linters calm


# ---------------------------------------------------------------------------
# Suite 1: corpus conformance — every file must measure −26.0 dBov
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_p501_annex_d_asl_minus_26_dbov(p501_annex_d: list[Path]) -> None:
    """Each Annex D file, pre-filtered per its bandwidth tag, must measure
    −26.0 dBov within the tolerance.
    """
    assert p501_annex_d, "no WAV files extracted from the P.501 Annex D archive"
    failures: list[str] = []
    for wav in p501_annex_d:
        band = _band_of(wav)
        frames, rate = sf.read(wav, always_2d=True)
        asl, _ = _measure(frames[:, 0], rate, band)
        if abs(asl - EXPECTED_ASL_DB) > TOLERANCE_DB:
            failures.append(f"{wav.name} [{band}]: {asl:+.3f} dB (expected {EXPECTED_ASL_DB})")
    assert not failures, "ASL out of tolerance:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# Suite 2: scaling linearity — ASL must shift by the applied gain
# ---------------------------------------------------------------------------


@pytest.mark.network
@pytest.mark.parametrize("offset_db", _SCALE_OFFSETS_DB, ids=lambda v: f"{v:+g}dB")
def test_p501_annex_d_scaling_linearity(p501_annex_d: list[Path], offset_db: float) -> None:
    """Scaling by ±dB must shift the ASL by exactly that offset.

    The corpus carries intrinsic per-file deviations (see
    `TOLERANCE_DB`), so linearity is asserted against the measured
    baseline of each file — the deviation must cancel exactly.

    For +30/+60 dB the samples exceed |x| > 1.0 (beyond full scale);
    the extended auto-calibration adapts `max_amplitude` so the result
    stays baseline + offset.
    """
    factor = 10.0 ** (offset_db / 20.0)
    over_range = offset_db > 0
    failures: list[str] = []
    for wav in p501_annex_d:
        band = _band_of(wav)
        frames, rate = sf.read(wav, always_2d=True)
        base, _ = _measure(frames[:, 0], rate, band)
        scaled = frames[:, 0] * factor
        if over_range:
            assert np.abs(scaled).max() > 1.0, f"{wav.name}: expected over-range samples"
        asl, _ = _measure(scaled, rate, band, auto_calibrate=over_range)
        if abs((asl - base) - offset_db) > LINEARITY_TOLERANCE_DB:
            failures.append(f"{wav.name} [{band}] {offset_db:+g} dB: {asl:+.3f} - base {base:+.3f} = {asl - base:+.3f} (expected {offset_db:+g})")
    assert not failures, "scaled ASL not linear:\n  " + "\n  ".join(failures)


@pytest.mark.network
def test_p501_annex_d_auto_calibration_triggers_on_over_range(p501_annex_d: list[Path]) -> None:
    """+60 dB scaling must exceed full scale and auto-calibration must
    raise `max_amplitude` above 1.0 while keeping the measurement valid
    (baseline + 60 dB, cancelling the corpus deviation).
    """
    wav = p501_annex_d[0]
    band = _band_of(wav)
    frames, rate = sf.read(wav, always_2d=True)
    base, _ = _measure(frames[:, 0], rate, band)
    scaled = frames[:, 0] * 10.0 ** (60.0 / 20.0)
    assert np.abs(scaled).max() > 1.0

    prefilter = PreFilter(band, float(rate))
    filtered = prefilter.process(scaled.astype("float32", copy=False))
    meter = ActiveSpeechLevelMeter(sample_rate=float(rate), max_amplitude=1.0, auto_calibrate=True)
    for k in range(0, len(filtered), 65536):
        meter.process_block(filtered[k : k + 65536])
    result = meter.finish()

    assert meter.max_amplitude > 1.0, "auto-calibration did not adapt max_amplitude"
    assert result.active_speech_level_db == pytest.approx(base + 60.0, abs=LINEARITY_TOLERANCE_DB)


# ---------------------------------------------------------------------------
# Sanity: tolerance confirmation helper (not a test by itself)
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_p501_corpus_deviation_report(p501_annex_d: list[Path]) -> None:
    """Print the per-file deviation to confirm the tolerance choice."""
    for wav in p501_annex_d:
        band = _band_of(wav)
        frames, rate = sf.read(wav, always_2d=True)
        asl, activity = _measure(frames[:, 0], rate, band)
        deviation = asl - EXPECTED_ASL_DB
        print(f"{wav.name} [{band}] fs={rate}: ASL {asl:+.3f} dB, dev {deviation:+.3f} dB, activity {activity * 100:.1f}%")


# ---------------------------------------------------------------------------
# Suite 3: end-to-end CLI — measure/calibrate on the real corpus
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_p501_annex_d_cli_measure_json(p501_annex_d: list[Path], tmp_path: Path) -> None:
    """`p56-asl measure --format json --pre-filter <band>` must report
    −26.0 dBov (corpus tolerance) for every Annex D file.
    """
    runner = CliRunner()
    failures: list[str] = []
    for wav in p501_annex_d:
        band = _band_of(wav)
        result = runner.invoke(app, ["measure", str(wav), "--pre-filter", band, "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["pre_filter"] == band
        assert payload["results"], f"{wav.name}: no results"
        for r in payload["results"]:
            if abs(r["active_speech_level_db"] - EXPECTED_ASL_DB) > TOLERANCE_DB:
                failures.append(f"{wav.name} [{band}] ch{r['channel']}: {r['active_speech_level_db']:+.3f} dB (expected {EXPECTED_ASL_DB})")
    assert not failures, "CLI ASL out of tolerance:\n  " + "\n  ".join(failures)


@pytest.mark.network
@pytest.mark.parametrize("gain_db", [-30.0, 30.0], ids=["-30dB", "+30dB"])
def test_p501_annex_d_cli_calibrate_measure_linearity(p501_annex_d: list[Path], tmp_path: Path, gain_db: float) -> None:
    """`p56-asl calibrate <in> <gain> <out>` followed by `measure` must
    reproduce baseline + gain (±0.1 dB) through the real CLI pipeline.

    The corpus is PCM_16; over-range samples (|x| > 1) are only
    representable in float WAVs, so +30 dB writes through a FLOAT
    intermediate — exercising the file-level auto-calibration path.
    """
    runner = CliRunner()
    wav = p501_annex_d[0]
    band = _band_of(wav)

    src = tmp_path / "src.wav"
    frames, rate = sf.read(wav, always_2d=True)
    sf.write(src, frames, rate, subtype="FLOAT")

    base_result = runner.invoke(app, ["measure", str(src), "--pre-filter", band, "--format", "json"])
    assert base_result.exit_code == 0, base_result.output
    base = json.loads(base_result.output)["results"][0]["active_speech_level_db"]

    out = tmp_path / "scaled.wav"
    result = runner.invoke(app, ["calibrate", str(src), f"{gain_db:+g}", str(out), "--pre-filter", band])
    assert result.exit_code == 0, result.output

    after_result = runner.invoke(app, ["measure", str(out), "--pre-filter", band, "--format", "json"])
    assert after_result.exit_code == 0, after_result.output
    after = json.loads(after_result.output)["results"][0]["active_speech_level_db"]

    assert after == pytest.approx(base + gain_db, abs=LINEARITY_TOLERANCE_DB)


def _band_of(path: Path) -> str:
    """Map the filename bandwidth tag to the pre-filter band.

    The 2025-04 corpus tags bandwidth via `_SWB_48k` / `_FB_48k`; the
    narrowband signals are the 8 kHz `_flat_08k` / `_IRS_08k` files
    (no explicit `_NB` tag exists) and map to NB.
    """
    name = path.name.upper()
    if "_SWB" in name:
        return "SWB"
    if "_FB" in name:
        return "FB"
    if "_NB" in name or "_08K" in name:
        return "NB"
    pytest.fail(f"no bandwidth tag (_NB/_SWB/_FB/_08k) in {path.name}")


def _measure(samples: np.ndarray, rate: int, band: str, *, auto_calibrate: bool = False) -> tuple[float, float]:
    """Run the CLI-equivalent pipeline: pre-filter → ASL meter."""
    prefilter = PreFilter(band, float(rate))
    prefilter.reset()
    filtered = prefilter.process(samples.astype("float32", copy=False))
    meter = ActiveSpeechLevelMeter(
        sample_rate=float(rate),
        max_amplitude=1.0,
        auto_calibrate=auto_calibrate,
    )
    for k in range(0, len(filtered), 65536):
        meter.process_block(filtered[k : k + 65536])
    result = meter.finish()
    return result.active_speech_level_db, result.activity_factor
