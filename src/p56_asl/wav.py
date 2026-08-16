"""WAV reading/writing for the CLI (stdlib-only, multi-channel).

Supports the formats produced/consumed by the reference toolchain:

- PCM 8/16/24/32-bit integer (WAVE_FORMAT_PCM, and the extensible
  variant ``WAVE_FORMAT_EXTENSIBLE`` with a ``fmt `` chunk >= 40 bytes)
- IEEE float 32/64-bit (``WAVE_FORMAT_IEEE_FLOAT``)

Reading returns ``(frames, sample_rate, bit_depth)`` where ``frames``
is a float64 array of shape ``(n_samples, n_channels)`` normalized to
[-1, 1] (integer samples divided by their maximum representable
value). Writing accepts the same normalization and quantizes to the
file's bit depth, clipping out-of-range values.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_WAVE_FORMAT_PCM = 0x0001
_WAVE_FORMAT_IEEE_FLOAT = 0x0003
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE

_INT_MAX = {8: 128, 16: 32_768, 24: 8_388_608, 32: 2_147_483_648}
_FLOAT_SIZES = {32: np.float32, 64: np.float64}
_WRITE_CHUNK = 65536  # bytes per write call, keeps memory flat


@dataclass(frozen=True)
class WavInfo:
    """Header facts of a read WAV file."""

    sample_rate: int
    channels: int
    bit_depth: int
    is_float: bool


def _read_chunks(data: memoryview) -> tuple[bytes, memoryview, WavInfo]:
    """Parses RIFF chunks; returns (fmt_chunk, data_view, info)."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        msg = "not a RIFF/WAVE file"
        raise ValueError(msg)
    pos = 12
    fmt_chunk = None
    data_view = None
    while pos + 8 <= len(data):
        cid = bytes(data[pos : pos + 4])
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            fmt_chunk = bytes(body)
        elif cid == b"data":
            data_view = body
        pos += 8 + size + (size & 1)  # chunks are word-aligned
    if fmt_chunk is None or data_view is None:
        msg = "missing fmt/data chunk"
        raise ValueError(msg)
    fmt_tag, channels, sample_rate, _, _, bits = struct.unpack_from("<HHIIHH", fmt_chunk, 0)
    if fmt_tag == _WAVE_FORMAT_EXTENSIBLE and len(fmt_chunk) >= 40:
        fmt_tag = struct.unpack_from("<H", fmt_chunk, 24)[0]
    is_float = fmt_tag == _WAVE_FORMAT_IEEE_FLOAT
    if not is_float and fmt_tag != _WAVE_FORMAT_PCM:
        msg = f"unsupported WAV format tag {fmt_tag:#06x}"
        raise ValueError(msg)
    if channels < 1:
        msg = f"invalid channel count {channels}"
        raise ValueError(msg)
    if bits not in {8, 16, 24, 32} and not is_float:
        msg = f"unsupported integer bit depth {bits}"
        raise ValueError(msg)
    if is_float and bits not in _FLOAT_SIZES:
        msg = f"unsupported float size {bits}"
        raise ValueError(msg)
    return fmt_chunk, data_view, WavInfo(sample_rate, channels, bits, is_float)


def read_wav(path: str | Path) -> tuple[np.ndarray, WavInfo]:
    """Reads a WAV file; returns ``(frames, info)``.

    ``frames`` is float64, shape ``(n_samples, channels)``, normalized
    to [-1, 1] for integer data, unchanged for float data.
    """
    raw = Path(path).read_bytes()
    _, body, info = _read_chunks(memoryview(raw))
    n_ch = info.channels
    if info.is_float:
        frames = np.frombuffer(body, dtype=f"<f{info.bit_depth // 8}")
    else:
        if info.bit_depth == 8:
            frames = np.frombuffer(body, dtype=np.uint8).astype(np.int16) - 128
        elif info.bit_depth == 16:
            frames = np.frombuffer(body, dtype="<i2").astype(np.int32)
        elif info.bit_depth == 24:
            b = np.frombuffer(body, dtype=np.uint8).reshape(-1, 3)
            frames = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)
            # sign-extend from 24 to 32 bits
            frames[frames >= 1 << 23] -= 1 << 24
        else:  # 32
            frames = np.frombuffer(body, dtype="<i4")
        frames = frames / float(_INT_MAX[info.bit_depth])
    if len(frames) % n_ch:
        frames = frames[: len(frames) - (len(frames) % n_ch)]
    return frames.reshape(-1, n_ch).astype(np.float64), info


def write_wav(path: str | Path, frames: np.ndarray, info: WavInfo, *, clip: bool = True) -> None:
    """Writes ``frames`` (float64, ``(n, channels)``) as a WAV file.

    Integer formats are written as plain PCM (the reference tools read
    both variants and plain PCM interoperates best). Float formats are
    written with ``WAVE_FORMAT_IEEE_FLOAT``. Out-of-range values are
    clipped before quantization unless ``clip=False`` (then they wrap).
    """
    frames = np.ascontiguousarray(frames, dtype=np.float64)
    if frames.ndim == 1:
        frames = frames[:, np.newaxis]
    n, n_ch = frames.shape
    if n_ch != info.channels:
        msg = f"channel mismatch: {n_ch} frames vs {info.channels} header"
        raise ValueError(msg)
    if info.is_float:
        dtype = _FLOAT_SIZES[info.bit_depth]
        payload = frames.astype(dtype).tobytes()
    else:
        q = _INT_MAX[info.bit_depth]
        scaled = frames * q
        if clip:
            scaled = np.clip(scaled, -q, q - 1)
        scaled = np.rint(scaled)
        if info.bit_depth == 8:
            payload = (scaled.astype(np.int16) + 128).astype(np.uint8).tobytes()
        elif info.bit_depth == 16:
            payload = scaled.astype("<i2").tobytes()
        elif info.bit_depth == 24:
            i32 = scaled.astype("<i4")
            b = np.empty((len(i32), 4), dtype=np.uint8)
            b[:, :3] = np.frombuffer(i32.tobytes(), dtype=np.uint8).reshape(-1, 4)[:, :3]
            payload = b[:, :3].tobytes()
        else:  # 32
            payload = scaled.astype("<i4").tobytes()
    byte_rate = info.sample_rate * n_ch * info.bit_depth // 8
    block_align = n_ch * info.bit_depth // 8
    fmt_tag = _WAVE_FORMAT_IEEE_FLOAT if info.is_float else _WAVE_FORMAT_PCM
    fmt = struct.pack("<HHIIHH", fmt_tag, n_ch, info.sample_rate, byte_rate, block_align, info.bit_depth)
    data_len = len(payload)
    with Path(path).open("wb") as fh:
        fh.write(b"RIFF")
        fh.write(struct.pack("<I", 36 + data_len))
        fh.write(b"WAVEfmt ")
        fh.write(struct.pack("<I", len(fmt)))
        fh.write(fmt)
        fh.write(b"data")
        fh.write(struct.pack("<I", data_len))
        for i in range(0, data_len, _WRITE_CHUNK):
            fh.write(payload[i : i + _WRITE_CHUNK])
