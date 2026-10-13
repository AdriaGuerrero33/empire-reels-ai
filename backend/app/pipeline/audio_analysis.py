"""Energía de la voz (RMS) y pausas, a partir del WAV mono de 16 kHz."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

HOP_S = 0.05  # resolución de la curva de energía


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return x, sr


def energy_curve(path: Path) -> dict:
    """Curva RMS en dBFS cada 50 ms."""
    x, sr = load_wav(path)
    hop = int(sr * HOP_S)
    if len(x) < hop:
        return {"hop": HOP_S, "db": []}
    frames = len(x) // hop
    xs = x[: frames * hop].reshape(frames, hop)
    rms = np.sqrt(np.mean(xs ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    return {"hop": HOP_S, "db": np.round(db, 1).tolist()}


def span_energy(curve: dict, start: float, end: float) -> float:
    db = curve.get("db") or []
    if not db:
        return -60.0
    hop = curve["hop"]
    a, b = int(start / hop), max(int(start / hop) + 1, int(end / hop))
    seg = db[a:b]
    if not seg:
        return -60.0
    arr = np.array(seg)
    voiced = arr[arr > -45]
    return float(np.mean(voiced)) if len(voiced) else float(np.mean(arr))


def loudness_stats(curve: dict) -> dict:
    db = np.array(curve.get("db") or [-60.0])
    voiced = db[db > -45]
    if not len(voiced):
        voiced = db
    return {"voiced_mean_db": round(float(np.mean(voiced)), 1),
            "voiced_p90_db": round(float(np.percentile(voiced, 90)), 1),
            "voiced_p10_db": round(float(np.percentile(voiced, 10)), 1),
            "voiced_ratio": round(float(len(db[db > -45]) / max(1, len(db))), 3)}
