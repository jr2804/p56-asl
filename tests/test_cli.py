"""CLI tests for `measure` and `calibrate` (Typer's CliRunner)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from p56_asl.cli.app import app
from p56_asl.wav import WavInfo, read_wav, write_wav

pytest.importorskip("p56_asl._native", reason="native extension not built")

_FS = 16_000

runner = CliRunner()


def test_measure_text(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src)])
    assert result.exit_code == 0, result.output
    assert "Active speech level" in result.output
    assert "Channel 1" in result.output


def test_measure_aliases(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    for alias in ("calc", "calculate"):
        result = runner.invoke(app, [alias, str(src)])
        assert result.exit_code == 0, result.output
        assert "Active speech level" in result.output


def test_measure_json(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech(channels=2))
    result = runner.invoke(app, ["measure", str(src), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["channels"] == [1, 2]
    assert len(payload["results"]) == 2
    for r in payload["results"]:
        assert np.isfinite(r["active_speech_level_db"])
        assert "activity_factor" in r


def test_measure_stereo_channel_selection(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech(channels=2))
    result = runner.invoke(app, ["measure", str(src), "--channels", "2"])
    assert result.exit_code == 0, result.output
    assert "Channel 1:" not in result.output
    assert "Channel 2:" in result.output


def test_measure_channel_list_with_blanks(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech(channels=2))
    result = runner.invoke(app, ["measure", str(src), "--channels", " 2 , 1 "])
    assert result.exit_code == 0, result.output
    assert "Channel 1:" in result.output
    assert "Channel 2:" in result.output


def test_measure_channel_out_of_range(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--channels", "3"])
    assert result.exit_code != 0
    assert "out of range" in result.output


def test_measure_channel_garbage(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--channels", "1,,2"])
    assert result.exit_code != 0


def test_measure_time_window(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    sig = _speech(n=_FS)  # 1 s
    _write(src, sig)
    full = runner.invoke(app, ["measure", str(src), "--format", "json"])
    part = runner.invoke(app, ["measure", str(src), "--time-start", "0.5", "--format", "json"])
    assert full.exit_code == 0, full.output
    assert part.exit_code == 0, part.output
    n_full = json.loads(full.output)["results"][0]["sample_count"]
    n_part = json.loads(part.output)["results"][0]["sample_count"]
    assert n_part == n_full // 2


def test_measure_time_duration(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech(n=_FS))
    result = runner.invoke(app, ["measure", str(src), "--time-duration", "0.25", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["results"][0]["sample_count"] == _FS // 4


def test_measure_fs_resampling(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech(fs=_FS))
    result = runner.invoke(app, ["measure", str(src), "--fs", "8000", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["results"][0]["sample_rate"] == 8000
    assert payload["results"][0]["sample_count"] == 24_000


def test_measure_pre_filter(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--pre-filter", "NB", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["pre_filter"] == "NB"
    assert np.isfinite(payload["results"][0]["active_speech_level_db"])


def test_measure_pre_filter_lowercase(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--pre-filter", "swb"])
    assert result.exit_code == 0, result.output
    assert "Pre-filter: SWB" in result.output


def test_measure_pre_filter_invalid(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--pre-filter", "MB"])
    assert result.exit_code != 0


def test_measure_nonexistent_file() -> None:
    result = runner.invoke(app, ["measure", "does-not-exist.wav"])
    assert result.exit_code != 0


# ---------------------------------------------------------------- calibrate


def test_calibrate_scales_by_gain(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "6.02", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = read_wav(src)
    b, _ = read_wav(dst)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() * 2.0, rtol=1e-2)


def test_calibrate_explicit_plus_sign(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+6.02", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = read_wav(src)
    b, _ = read_wav(dst)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() * 2.0, rtol=1e-2)


def test_calibrate_negative_gain(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "-6.02", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = read_wav(src)
    b, _ = read_wav(dst)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() / 2.0, rtol=1e-2)


def test_calibrate_alias_scale(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["scale", str(src), "0", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = read_wav(src)
    b, _ = read_wav(dst)
    np.testing.assert_allclose(b, a, atol=1e-4)


def test_calibrate_in_place(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    a, info = read_wav(src)
    result = runner.invoke(app, ["calibrate", str(src), "-20"])
    assert result.exit_code == 0, result.output
    b, info2 = read_wav(src)
    assert info.sample_rate == info2.sample_rate
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() / 10.0, rtol=1e-2)


def test_calibrate_selected_channels_only(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    sig = _speech(channels=2)
    _write(src, sig)
    result = runner.invoke(app, ["calibrate", str(src), "6.02", str(dst), "--channels", "1"])
    assert result.exit_code == 0, result.output
    a, _ = read_wav(src)
    b, _ = read_wav(dst)
    # channel 1 scaled by ~2x
    np.testing.assert_allclose(np.abs(b[:, 0]).max(), np.abs(a[:, 0]).max() * 2.0, rtol=1e-2)
    # channel 2 unchanged
    np.testing.assert_allclose(np.abs(b[:, 1]).max(), np.abs(a[:, 1]).max(), rtol=1e-2)


def test_calibrate_resample_channel_selection(tmp_path: Path) -> None:
    """Regression: with --fs, the *selected* (not k-th) channel must be scaled."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    sig = _speech(channels=2)
    _write(src, sig)
    result = runner.invoke(app, ["calibrate", str(src), "6.02", str(dst), "--channels", "2", "--fs", "8000"])
    assert result.exit_code == 0, result.output
    a, _ = read_wav(src)
    b, info = read_wav(dst)
    assert info.sample_rate == 8000
    # ch2 = 0.5 x (rolled) ch1; scaled by +6.02 dB it matches ch1's
    # (resampled) amplitude, proving the *selected* channel got the gain
    np.testing.assert_allclose(np.abs(b[:, 1]).max(), np.abs(b[:, 0]).max(), rtol=5e-2)


def test_calibrate_resample_rate_written(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech(fs=_FS))
    result = runner.invoke(app, ["calibrate", str(src), "0", str(dst), "--fs", "48000"])
    assert result.exit_code == 0, result.output
    _, info = read_wav(dst)
    assert info.sample_rate == 48_000


def test_calibrate_gain_roundtrip(tmp_path: Path) -> None:
    """+g then -g restores the signal (same rate, integer-safe depth)."""
    src = tmp_path / "in.wav"
    mid = tmp_path / "mid.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    assert runner.invoke(app, ["calibrate", str(src), "6.02", str(mid)]).exit_code == 0
    assert runner.invoke(app, ["calibrate", str(mid), "-6.02", str(dst)]).exit_code == 0
    a, _ = read_wav(src)
    b, _ = read_wav(dst)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max(), rtol=5e-2)


def test_calibrate_invalid_gain(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "loud", str(dst)])
    assert result.exit_code != 0


def test_calibrate_time_window(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    sig = _speech(n=_FS, channels=2)  # 1 s
    _write(src, sig)
    result = runner.invoke(app, ["calibrate", str(src), "0", str(dst), "--time-start", "0.5"])
    assert result.exit_code == 0, result.output
    b, info = read_wav(dst)
    assert info.channels == 2
    assert len(b) == _FS // 2


@pytest.mark.parametrize(
    ("bit_depth", "is_float"),
    [(8, False), (16, False), (24, False), (32, False), (32, True), (64, True)],
    ids=["pcm8", "pcm16", "pcm24", "pcm32", "float32", "float64"],
)
def test_calibrate_dtype_roundtrip(tmp_path: Path, bit_depth: int, is_float: bool) -> None:
    """Calibrate must preserve the file's dtype through read → scale → write."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech(), bit_depth=bit_depth, is_float=is_float)
    result = runner.invoke(app, ["calibrate", str(src), "-6.02", str(dst)])
    assert result.exit_code == 0, result.output
    a, info_a = read_wav(src)
    b, info_b = read_wav(dst)
    assert (info_b.bit_depth, info_b.is_float) == (bit_depth, is_float)
    assert info_b.channels == info_a.channels
    assert info_b.sample_rate == info_a.sample_rate
    atol = {8: 1 / 64, 16: 1 / 4096, 24: 1 / 65536}.get(bit_depth, 1e-6)
    np.testing.assert_allclose(b, a * 10.0 ** (-6.02 / 20.0), atol=atol)


def _speech(n: int = 48_000, fs: int = _FS, channels: int = 1, seed: int = 0) -> np.ndarray:
    """Deterministic speech-like multi-channel signal (envelope + noise)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    env = 0.5 * (1 + np.sin(2 * np.pi * 3 * t))  # slow syllable envelope
    sig = env * rng.standard_normal(n)
    sig = sig / np.abs(sig).max() * 0.25  # headroom for +6 dB calibration
    if channels == 1:
        return sig[:, np.newaxis]
    ch2 = np.roll(sig, n // 3) * 0.5  # decorrelated second channel
    return np.column_stack([sig, ch2])


def _write(path: Path, sig: np.ndarray, fs: int = _FS, bit_depth: int = 16, is_float: bool = False) -> None:
    write_wav(
        path,
        sig,
        WavInfo(sample_rate=fs, channels=sig.shape[1], bit_depth=bit_depth, is_float=is_float),
    )
