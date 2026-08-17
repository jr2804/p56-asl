#!/usr/bin/env python3
"""Generate the extended-mode illustration for docs/reference/extended-mode.md.

Builds a speech-like burst signal whose peak steps from 0.35 to 1.5 to 3.5,
runs the meter with ``auto_calibrate=True`` on it, and renders two panels:
the signal with its smoothed envelope and the adapting ``max_amplitude``
reference, and the histogram threshold grid in dB showing the +6.02 dB
shift at every calibration.

Output: ``docs/reference/extended-mode.svg`` (committed).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xy.pyplot as plt

from p56_asl import ActiveSpeechLevelMeter

try:
    ROOT = Path(__file__).parent.parent
except NameError:  # executed via markdown-exec during docs build
    ROOT = Path.cwd()

FS = 8_000.0
BLOCK = 256
# (start, end, peak amplitude): the peaks 1.5 and 3.5 trigger calibration.
PHASES = ((0.0, 0.7, 0.35), (0.7, 1.4, 1.5), (1.4, 2.1, 3.5))
OUT = ROOT / "docs" / "reference" / "extended-mode.svg"


def main() -> None:
    t, x = make_signal(FS)
    q = smoothing_envelope(x, FS)
    meter, t_edges, amps = run_meter(x, FS, BLOCK)

    ts, ys = step_xy(t_edges, amps)
    tq, qq = step_xy(t_edges, amps / 2.0)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)

    # Panel 1: signal, envelope, adapting reference.
    colors = ("#e8f0e8", "#e8f0ff", "#fff0e8")
    for (a0, a1, _), c in zip(PHASES, colors, strict=False):
        ax1.axvspan(a0, a1, color=c, lw=0)
    ax1.plot(t[::3], x[::3], color="#b0b6bd", lw=0.5, label="signal x")
    ax1.plot(t[::3], q[::3], color="#1f77b4", lw=1.2, label="smoothed envelope q")
    ax1.plot(ts, ys, color="#d62728", ls="--", lw=1.5, label="max_amplitude (reference)")
    ax1.annotate("peak 1.5", xy=(1.05, 1.5), xytext=(0.78, 2.35), arrowprops={"arrowstyle": "->"}, fontsize=9)
    ax1.annotate("peak 3.5", xy=(1.85, 3.5), xytext=(1.45, 4.35), arrowprops={"arrowstyle": "->"}, fontsize=9)
    ax1.set_ylabel("amplitude")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.set_title("Auto-calibrated amplitude reference ($max\\_amplitude$)", fontsize=10)

    # Panel 2: envelope and threshold grid in dB — each calibration shifts
    # the grid by +6.02 dB (thresholds x2).
    db_env = 20.0 * np.log10(np.maximum(q, 1e-6))
    ax2.plot(t[::3], db_env[::3], color="#1f77b4", lw=1.0, label="envelope $20\\log_{10} q$")
    for k in (1, 2, 3, 4):
        tk, yk = step_xy(t_edges, 20.0 * np.log10(np.maximum(amps / (2.0**k), 1e-6)))
        ax2.plot(tk, yk, color="#2ca02c", lw=1.0, alpha=0.85 if k == 1 else 0.45)
    ax2.plot([], [], color="#2ca02c", lw=1.0, label="thresholds $c_k = max\\_amplitude \\cdot 2^{-k}$")
    for tc in (0.7, 1.4):
        ax2.axvline(tc, color="#999", ls=":", lw=1.0)
    ax2.annotate("+6.02 dB\n(thresholds \u00d72)", xy=(0.7, 8.0), xytext=(0.32, 9.5), fontsize=9, arrowprops={"arrowstyle": "->"})
    ax2.annotate("+6.02 dB\n(thresholds \u00d72)", xy=(1.4, 8.0), xytext=(1.02, 9.5), fontsize=9, arrowprops={"arrowstyle": "->"})
    ax2.set_ylim(-90, 14)
    ax2.set_xlim(0.0, PHASES[-1][1])
    ax2.set_ylabel("level re 1.0 (dB)")
    ax2.set_xlabel("time (s)")
    ax2.set_xticks([0.0, 0.7, 1.4, 2.1])
    ax2.legend(loc="lower left", fontsize=8)

    fig.tight_layout()
    plt.savefig(OUT)
    plt.close(fig)

    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KiB)")
    print(f"max_amplitude steps: {amps[0]:.1f} -> {amps[-1]:.1f}")
    print(f"measurement (auto_calibrate=True):  ASL={meter.finish().active_speech_level_db:.2f} dB")
    m = ActiveSpeechLevelMeter(sample_rate=float(FS))
    for i in range(0, len(x), BLOCK):
        m.process_block(x[i : i + BLOCK].astype(np.float32))
    print(f"measurement (auto_calibrate=False): ASL={m.finish().active_speech_level_db:.2f} dB")


def make_signal(fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic speech-like burst train with step-rising peak."""
    n = int(round(PHASES[-1][1] * fs))
    x = np.zeros(n)
    rng = np.random.default_rng(42)
    for t0, t1, peak in PHASES:
        t = t0
        while t < t1 - 0.15:
            dur = 0.09 + 0.02 * rng.random()
            gap = 0.04 + 0.04 * rng.random()
            i0 = int(round(t * fs))
            i1 = min(i0 + int(round(dur * fs)), n)
            tt = np.arange(i1 - i0) / fs
            env = 0.5 * (1.0 - np.cos(2 * np.pi * tt / dur))
            carrier = 180.0 + 40.0 * rng.random()
            x[i0:i1] = peak * env * np.sin(2 * np.pi * carrier * tt)
            t += dur + gap
    return np.arange(n) / fs, x


def smoothing_envelope(x: np.ndarray, fs: float) -> np.ndarray:
    """Process 2 envelope ``q`` — exact recursion, f64 (same as the core)."""
    g = np.exp(-1.0 / (fs * 0.03))
    p = 0.0
    q = 0.0
    out = np.empty_like(x)
    for i, ax in enumerate(np.abs(x)):
        p = g * p + (1.0 - g) * ax
        q = g * q + (1.0 - g) * p
        out[i] = q
    return out


def run_meter(x: np.ndarray, fs: float, block: int) -> tuple[ActiveSpeechLevelMeter, np.ndarray, np.ndarray]:
    """Feed the meter blockwise; return (meter, time edges, max_amplitude steps)."""
    meter = ActiveSpeechLevelMeter(sample_rate=float(fs), auto_calibrate=True)
    edges = [0.0]
    amps = [meter.max_amplitude]
    for i in range(0, len(x), block):
        meter.process_block(x[i : i + block].astype(np.float32))
        edges.append(min(i + block, len(x)) / fs)
        amps.append(meter.max_amplitude)
    return meter, np.asarray(edges), np.asarray(amps)


def step_xy(t_edges: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Expand (edge, value) pairs into a plotting-ready step curve."""
    return np.repeat(t_edges, 2)[1:], np.repeat(v, 2)[:-1]


if __name__ == "__main__":
    main()
