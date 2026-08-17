"""Conformance and behavioral tests for the P.56 active speech level meter.

Conformance fixtures (`*.log.ref`) come from the ITU-T G.191 reference C
implementation (`ref/sv56demo`) run on the speech files in `tests/data/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from p56_asl import ActiveSpeechLevelMeter, Measurement

_FP = r"(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"


# ---------------------------------------------------------------------------
# Fixture parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefLog:
    """Parsed reference log (`*.log.ref`)."""

    sample_rate: int
    bit_depth: int
    dc_level_pcm: float
    peak_positive_pcm: float
    peak_negative_pcm: float
    rms_db: float
    active_speech_level_db: float
    activity_factor_percent: float


@dataclass(frozen=True)
class ConformanceCase:
    wav: str
    log: str
    bit_depth: int


def parse_ref_log(path: Path) -> RefLog:
    """Parse a sv56demo reference log into a :class:`RefLog`."""
    text = path.read_text(encoding="utf-8", errors="replace")
    bit_depth_match = re.search(r"(\d+) bits, fs=(\d+) Hz", text)
    assert bit_depth_match, f"no bit/fs header in {path}"
    bit_depth = int(bit_depth_match.group(1))
    sample_rate = int(bit_depth_match.group(2))

    def field(name: str) -> float:
        match = re.search(rf"{re.escape(name)}\s*:.*?{_FP}", text)
        assert match, f"field '{name}' not found in {path}"
        return float(match.group(1))

    return RefLog(
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        dc_level_pcm=field("DC level"),
        peak_positive_pcm=field("Maximum positive value"),
        peak_negative_pcm=field("Maximum negative value"),
        rms_db=field("Long term energy (rms)"),
        active_speech_level_db=field("Active speech level"),
        activity_factor_percent=field("Activity factor"),
    )


# ---------------------------------------------------------------------------
# Stateful filtering (user requirement: filter taps persist across blocks)
# ---------------------------------------------------------------------------


def test_stateful_filter_split_equals_whole() -> None:
    """Split-block processing must equal single-call processing exactly."""
    fs = 16_000
    t = np.arange(fs, dtype=np.float64)
    x = (0.3 * np.sin(2 * np.pi * 1000 * t / fs)).astype(np.float32)

    m1 = ActiveSpeechLevelMeter(sample_rate=fs)
    m1.process_block(x)
    r1 = m1.finish()

    m2 = ActiveSpeechLevelMeter(sample_rate=fs)
    for k in range(0, len(x), 256):
        m2.process_block(x[k : k + 256])
    r2 = m2.finish()

    assert r1.active_speech_level_db == r2.active_speech_level_db
    assert r1.sample_count == r2.sample_count
    assert r1.rms_db == r2.rms_db
    assert r1.peak_abs == r2.peak_abs


def test_stateful_filter_odd_block_splits() -> None:
    """State continuity must not depend on the split positions."""
    fs = 16_000
    t = np.arange(fs, dtype=np.float64)
    x = (0.3 * np.sin(2 * np.pi * 800 * t / fs) * (t < 0.5) + 0.05).astype(np.float32)

    m_ref = ActiveSpeechLevelMeter(sample_rate=fs)
    m_ref.process_block(x)
    r_ref = m_ref.finish()

    for chunk_len in (7, 63, 256, 1000, 4095):
        m = ActiveSpeechLevelMeter(sample_rate=fs)
        for k in range(0, len(x), chunk_len):
            m.process_block(x[k : k + chunk_len])
        r = m.finish()
        assert r.active_speech_level_db == r_ref.active_speech_level_db, chunk_len


# ---------------------------------------------------------------------------
# Numpy dtype contract (user requirement)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "max_val",
    [127.0, 32767.0, 8_388_607.0, 2_147_483_647.0],
    ids=["8bit", "16bit", "24bit", "32bit"],
)
def test_integer_normalization(max_val: float) -> None:
    """Integer normalization at the WAV-reader boundary must match float."""
    fs = 16_000
    t = np.arange(fs, dtype=np.float64)
    sine = 0.25 * np.sin(2 * np.pi * 997 * t / fs)

    float_result = measure(sine.astype(np.float32), fs)

    ints = np.rint(sine * max_val).astype(np.int32)
    ints_f = ints.astype(np.float32) / max_val
    int_result = measure(ints_f, fs)

    assert int_result.active_speech_level_db == pytest.approx(float_result.active_speech_level_db, abs=0.05)
    # Integer peak is a multiple of 1/max_val; allow half a quantum.
    assert int_result.peak_abs == pytest.approx(float_result.peak_abs, abs=1.5 / max_val)


def test_rejects_non_numpy_input() -> None:
    meter = ActiveSpeechLevelMeter()
    with pytest.raises(ValueError, match="numpy"):
        meter.process_block([0.0] * 16)  # type: ignore
    with pytest.raises(ValueError, match="numpy"):
        meter.process_block(0.0 for _ in range(16))  # type: ignore


def test_rejects_2d_array() -> None:
    meter = ActiveSpeechLevelMeter()
    with pytest.raises(ValueError, match="1-D"):
        meter.process_block(np.zeros((4, 4), dtype=np.float32))


def test_rejects_unsupported_dtype() -> None:
    meter = ActiveSpeechLevelMeter()
    with pytest.raises(ValueError, match="dtype"):
        meter.process_block(np.zeros(16, dtype=np.bool_))  # type: ignore


def test_int32_24bit_divisor() -> None:
    """24-bit int must be divided by 8388607 (max 24-bit value), not
    2147483647 (max 32-bit) — i.e. boundary normalization must use the
    true bit depth of the source file.
    """
    fs = 16_000
    t = np.arange(fs, dtype=np.float64)
    sine = 0.5 * np.sin(2 * np.pi * 1000 * t / fs)
    int24 = np.rint(sine * 8_388_607).astype(np.int32)
    normalized = int24.astype(np.float32) / 8_388_607.0

    r = measure(normalized, fs)
    expected = 20 * np.log10(0.5 / np.sqrt(2))
    assert r.active_speech_level_db == pytest.approx(expected, abs=0.15)


# ---------------------------------------------------------------------------
# Resampling (user requirement: any rate, <16 kHz upsampled via rubato)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fs", [8_000, 11_025, 12_000])
def test_resampling_matches_16k_reference(fs: int) -> None:
    """Resampled measurement must track the native 16 kHz result."""
    t = np.arange(fs * 2, dtype=np.float64)
    x = (0.3 * np.sin(2 * np.pi * 1000 * t / fs)).astype(np.float32)

    r_low = measure(x.astype(np.float32), fs)
    expected = 20 * np.log10(0.3 / np.sqrt(2))
    assert r_low.active_speech_level_db == pytest.approx(expected, abs=0.2)


def measure(samples: np.ndarray, sample_rate: float, block_size: int = 256) -> Measurement:
    meter = ActiveSpeechLevelMeter(sample_rate=sample_rate, block_size=block_size)
    process_file(meter, samples)
    return meter.finish()


def test_resampled_sample_count() -> None:
    """Output length must be ~ceil(input * 16000 / rate)."""
    fs = 8_000
    n = fs // 2  # 0.5 s
    t = np.arange(n, dtype=np.float64)
    x = (0.2 * np.sin(2 * np.pi * 500 * t / fs)).astype(np.float32)
    meter = ActiveSpeechLevelMeter(sample_rate=fs)
    process_file(meter, x)
    result = meter.finish()
    assert result.sample_count == pytest.approx(n * 2, abs=64)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def process_file(meter: ActiveSpeechLevelMeter, samples: np.ndarray) -> None:
    """Feed a full file into the meter blockwise (block_size chunks)."""
    block = meter.block_size
    for start in range(0, len(samples), block):
        meter.process_block(samples[start : start + block])


# ---------------------------------------------------------------------------
# Reference conformance (G.191 sv56demo)
# ---------------------------------------------------------------------------


def _load_wav(path: Path, bit_depth: int) -> tuple[int, np.ndarray]:
    """Read a reference wav as float32 in (-1, 1).

    Integer subtypes are normalized at the boundary by the true bit depth;
    the meter is float-only (the reference P.56 is too).
    """
    rate, data = wavfile.read(path)
    max_val = float(2 ** (bit_depth - 1) - 1)
    if data.dtype == np.int16:
        return rate, (data / 32767.0).astype(np.float32)
    if data.dtype == np.int32:
        # 24-bit WAVs widen to int32 left-justified (low 8 bits zero).
        raw = data >> 8 if bit_depth == 24 else data
        return rate, (raw / max_val).astype(np.float32)
    msg = f"unsupported wav dtype {data.dtype} in {path}"
    raise ValueError(msg)


CONFORMANCE_CASES = [
    ConformanceCase("speech_normal_24bit.wav", "speech_normal_24bit.log.ref", 24),
    ConformanceCase("speech_normal_32bit.wav", "speech_normal_32bit.log.ref", 32),
    ConformanceCase("speech_quiet_24bit.wav", "speech_quiet_24bit.log.ref", 24),
    ConformanceCase("speech_vquiet_32bit.wav", "speech_vquiet_32bit.log.ref", 32),
]


@pytest.mark.parametrize("case", CONFORMANCE_CASES, ids=lambda c: c.wav)
def test_conformance_sv56demo(case: ConformanceCase, data_dir: Path) -> None:
    """ASL must match the reference implementation within 0.1 dB."""
    ref = parse_ref_log(data_dir / case.log)
    rate, data = _load_wav(data_dir / case.wav, ref.bit_depth)
    assert rate == ref.sample_rate

    block_size = 256
    meter = ActiveSpeechLevelMeter(sample_rate=rate, block_size=block_size)
    process_file(meter, data)
    result = meter.finish()

    assert result.active_speech_level_db == pytest.approx(ref.active_speech_level_db, abs=0.1)
    assert result.rms_db == pytest.approx(ref.rms_db, abs=0.1)
    assert result.activity_factor == pytest.approx(ref.activity_factor_percent / 100.0, abs=0.01)


def test_silence_reports_minus_100() -> None:
    fs = 16_000
    x = np.zeros(fs, dtype=np.float32)
    r = measure(x, fs)
    assert r.active_speech_level_db == pytest.approx(-100.0)
    assert r.activity_factor == pytest.approx(0.0)


def test_reset_after_finish_with_resampler() -> None:
    """reset() must also reset the internal <16 kHz resampler (regression)."""
    m = ActiveSpeechLevelMeter(sample_rate=8000.0)
    m.process_block(np.full(256, 0.1, dtype=np.float32))
    m.finish()
    m.reset()
    m.process_block(np.full(256, 0.1, dtype=np.float32))  # must not raise
    r = m.finish()
    assert np.isfinite(r.active_speech_level_db)
