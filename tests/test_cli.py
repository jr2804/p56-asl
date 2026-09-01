"""CLI tests for `measure` and `calibrate` (Typer's CliRunner)."""

from __future__ import annotations

import importlib
import importlib.metadata as md
import json
import re
import runpy
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

import p56_asl
import p56_asl.__about__ as about
from p56_asl.cli import app as cli_app
from p56_asl.cli.app import app, main
from p56_asl.cli.args import parse_channels

_FS = 16_000

runner = CliRunner()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip()  # echoes a version string like "0.0.0"


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # Typer's no_args_is_help shows the usage panel (exit code 2 via CliRunner).
    assert "usage" in result.output.lower() or "measure" in result.output.lower()


def test_main_entrypoint() -> None:
    """The CLI app `main` is wired; --version exercises the callback."""
    assert callable(main)
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_about_metadata() -> None:
    """Importing __about__ exercises version metadata wiring."""
    assert about.__title__ == "p56_asl"
    assert about.__version__
    assert about.__license__ == "MIT"


def test_version_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """PackageNotFoundError at import time falls back to 0.0.0."""

    def boom(name: str) -> str:  # pragma: no cover - only used when patched
        raise md.PackageNotFoundError

    monkeypatch.setattr(md, "version", boom)
    importlib.reload(p56_asl)
    assert p56_asl.__version__ == "0.0.0"


def test_get_version_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """--version falls back to 0.0.0 when package metadata is missing."""

    def boom(name: str) -> str:  # pragma: no cover - only used when patched
        raise md.PackageNotFoundError

    monkeypatch.setattr(cli_app, "version", boom)
    assert cli_app._get_version() == "0.0.0"


def test_main_runs_app() -> None:
    """Calling main() runs the Typer app (help shown, exit raised)."""
    with pytest.raises(SystemExit):
        main()


def test_python_m_entrypoint() -> None:
    """Python -m p56_asl runs the CLI (__main__.py)."""
    with pytest.raises(SystemExit):
        runpy.run_module("p56_asl.__main__", run_name="__main__")


def test_parse_channels_rejects_non_integer() -> None:
    """A channel element that is not an integer is rejected."""
    with pytest.raises(Exception, match="integers"):
        parse_channels("1,abc", 2)


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
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() * 2.0, rtol=1e-2)


def test_calibrate_explicit_plus_sign(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+6.02", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() * 2.0, rtol=1e-2)


def test_calibrate_negative_gain(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "-6.02", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() / 2.0, rtol=1e-2)


def test_calibrate_alias_scale(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["scale", str(src), "0", str(dst)])
    assert result.exit_code == 0, result.output
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
    np.testing.assert_allclose(b, a, atol=1e-4)


def test_calibrate_in_place(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    a, _ = sf.read(src, always_2d=True)
    result = runner.invoke(app, ["calibrate", str(src), "-20"])
    assert result.exit_code == 0, result.output
    b, _ = sf.read(src, always_2d=True)
    np.testing.assert_allclose(np.abs(b).max(), np.abs(a).max() / 10.0, rtol=1e-2)


def test_calibrate_selected_channels_only(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    sig = _speech(channels=2)
    _write(src, sig)
    result = runner.invoke(app, ["calibrate", str(src), "6.02", str(dst), "--channels", "1"])
    assert result.exit_code == 0, result.output
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
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
    a, _ = sf.read(src, always_2d=True)
    b, rate = sf.read(dst, always_2d=True)
    assert rate == 8000
    # ch2 = 0.5 x (rolled) ch1; scaled by +6.02 dB it matches ch1's
    # (resampled) amplitude, proving the *selected* channel got the gain
    np.testing.assert_allclose(np.abs(b[:, 1]).max(), np.abs(b[:, 0]).max(), rtol=5e-2)


def test_calibrate_resample_rate_written(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech(fs=_FS))
    result = runner.invoke(app, ["calibrate", str(src), "0", str(dst), "--fs", "48000"])
    assert result.exit_code == 0, result.output
    _, rate = sf.read(dst, always_2d=True)
    assert rate == 48_000


def test_calibrate_gain_roundtrip(tmp_path: Path) -> None:
    """+g then -g restores the signal (same rate, integer-safe depth)."""
    src = tmp_path / "in.wav"
    mid = tmp_path / "mid.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    assert runner.invoke(app, ["calibrate", str(src), "6.02", str(mid)]).exit_code == 0
    assert runner.invoke(app, ["calibrate", str(mid), "-6.02", str(dst)]).exit_code == 0
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
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
    b, _ = sf.read(dst, always_2d=True)
    assert sf.info(dst).channels == 2
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
    a, _ = sf.read(src, always_2d=True)
    b, _ = sf.read(dst, always_2d=True)
    assert _dtype_of(sf.info(dst).subtype) == (bit_depth, is_float)
    assert sf.info(dst).channels == sf.info(src).channels
    assert sf.info(dst).samplerate == sf.info(src).samplerate
    atol = {8: 1 / 64, 16: 1 / 4096, 24: 1 / 65536}.get(bit_depth, 1e-6)
    np.testing.assert_allclose(b, a * 10.0 ** (-6.02 / 20.0), atol=atol)


@pytest.mark.parametrize("subtype", ["FLOAT", "PCM_16", "PCM_24"])
def test_calibrate_subtype_override(tmp_path: Path, subtype: str) -> None:
    """--subtype controls the output dtype (FLOAT must not clip)."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+6.02", str(dst), "--subtype", subtype])
    assert result.exit_code == 0, result.output
    info = sf.info(dst)
    assert info.subtype == subtype


def test_calibrate_subtype_float_no_clip(tmp_path: Path) -> None:
    """FLOAT output must not clip when overdriving hard."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+20", str(dst), "--subtype", "FLOAT"])
    assert result.exit_code == 0, result.output
    assert "clipping" not in result.output.lower()


def test_calibrate_invalid_prefilter(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "0", str(dst), "--pre-filter", "bad"])
    assert result.exit_code != 0
    # Strip ANSI styling: rich may wrap the flag token in escape sequences,
    # splitting the literal substring "pre-filter" across style runs.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output).lower()
    assert "pre-filter" in plain


def test_measure_invalid_prefilter(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--pre-filter", "bad"])
    assert result.exit_code != 0


def test_measure_time_start_beyond_eof(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--time-start", "1000"])
    assert result.exit_code != 0
    assert "beyond" in result.output.lower()


def test_calibrate_time_start_beyond_eof(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "0", str(dst), "--time-start", "1000"])
    assert result.exit_code != 0


def test_calibrate_clip_warning_pcm(tmp_path: Path) -> None:
    """Clipping warning fires for fixed-point output when over-driven."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+100", str(dst)])
    assert result.exit_code == 0, result.output
    assert "clipping" in result.output.lower()


def test_calibrate_in_place_with_resample(tmp_path: Path) -> None:
    """In-place calibrate with --fs resamples + scales, overwriting source."""
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+6.02", "--fs", "8000"])
    assert result.exit_code == 0, result.output
    after, rate = sf.read(src, always_2d=True)
    assert rate == 8000
    assert len(after) == 24_000  # 3 s @ 16k mono -> 1.5 s @ 8k


def test_calibrate_in_place_clipping(tmp_path: Path) -> None:
    """In-place calibrate warns on clipping (PCM path)."""
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+100"])
    assert result.exit_code == 0, result.output
    assert "clipping" in result.output.lower()


def test_measure_fs_and_prefilter(tmp_path: Path) -> None:
    """--fs and --pre-filter combine; resampler flush tail is measured."""
    src = tmp_path / "in.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["measure", str(src), "--fs", "8000", "--pre-filter", "NB", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["results"][0]["sample_rate"] == 8000
    assert payload["results"][0]["active_speech_level_db"] < 0.0


def test_calibrate_fs_and_prefilter(tmp_path: Path) -> None:
    """Calibrate with --fs and --pre-filter: resampler tail is flushed."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _write(src, _speech())
    result = runner.invoke(app, ["calibrate", str(src), "+6.02", str(dst), "--fs", "8000", "--pre-filter", "NB"])
    assert result.exit_code == 0, result.output
    assert sf.info(dst).samplerate == 8000


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


def _dtype_of(subtype: str) -> tuple[int, bool]:
    """(bit_depth, is_float) from a soundfile subtype string."""
    if subtype == "FLOAT":
        return 32, True
    if subtype == "DOUBLE":
        return 64, True
    return int(subtype.split("_")[1].lstrip("U")), False


def _write(path: Path, sig: np.ndarray, fs: int = _FS, bit_depth: int = 16, is_float: bool = False) -> None:
    subtype = ("FLOAT" if bit_depth == 32 else "DOUBLE") if is_float else "PCM_U8" if bit_depth == 8 else f"PCM_{bit_depth}"
    sf.write(path, sig, fs, subtype=subtype)
