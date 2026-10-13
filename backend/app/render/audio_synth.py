"""Música y efectos de sonido sintetizados (originales: sin problemas de licencia).

Se cachean por (preset, duración). La música subida por el usuario a la biblioteca
se usa tal cual; su licencia es responsabilidad del usuario y se indica en la UI.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from ..config import get_settings

SR = 44100
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(note: str, octave: int) -> float:
    return 440.0 * 2 ** ((NOTE[note] + 12 * (octave + 1) - 69) / 12)


def chord(root: str, minor: bool, octave: int = 3) -> list[float]:
    r = NOTE[root]
    ints = [0, 3, 7, 10] if minor else [0, 4, 7, 11]
    names = list(NOTE)
    return [hz(names[(r + i) % 12], octave + (r + i) // 12) for i in ints]


def _env(n: int, a: float, r: float) -> np.ndarray:
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:min(na, n)] = np.linspace(0, 1, min(na, n))
    if nr:
        e[-min(nr, n):] *= np.linspace(1, 0, min(nr, n))
    return e


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    # FIR de ventana de Hann (vectorizado): suficiente para suavizar los armónicos del pad
    n = max(3, int(SR / cutoff))
    k = np.hanning(n)
    return np.convolve(x, k / k.sum(), mode="same")


def _pad(freqs: list[float], dur: float, bright: float = 0.35) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    x = np.zeros_like(t)
    for f in freqs:
        for det in (-0.003, 0.003):
            ff = f * (1 + det)
            x += np.sin(2 * np.pi * ff * t) + bright * 0.5 * np.sin(4 * np.pi * ff * t) + bright * 0.25 * np.sin(6 * np.pi * ff * t)
    x /= max(1, len(freqs) * 2)
    return x * _env(len(t), min(0.6, dur / 3), min(0.8, dur / 3))


def _pluck(f: float, dur: float, decay: float = 4.0, harm: float = 0.3) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    x = (np.sin(2 * np.pi * f * t) + harm * np.sin(4 * np.pi * f * t) + harm * 0.4 * np.sin(8 * np.pi * f * t))
    return x * np.exp(-decay * t) * _env(len(t), 0.004, 0.02)


def _kick(dur: float = 0.35) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    f = 50 + 90 * np.exp(-28 * t)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-9 * t)


def _hat(dur: float = 0.06, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = rng.standard_normal(n)
    x = np.diff(x, prepend=0)  # paso alto simple
    return x * np.exp(-60 * np.arange(n) / SR) * 0.3


def _snare(dur: float = 0.18, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    return (0.6 * rng.standard_normal(n) * np.exp(-22 * t) + 0.4 * np.sin(2 * np.pi * 190 * t) * np.exp(-30 * t))


def _place(buf: np.ndarray, x: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(x))
    buf[i:j] += gain * x[: j - i]


PRESETS = {
    # (progresión, bpm, menor?, batería, arpegio)
    "upbeat_pulse": ([("A", True), ("F", False), ("C", False), ("G", False)], 112, "four", "eighths"),
    "corporate_drive": ([("C", False), ("G", False), ("A", True), ("F", False)], 104, "drive", "quarters"),
    "ambient_pad": ([("D", False), ("A", False), ("B", True), ("G", False)], 70, None, None),
    "emotional_keys": ([("A", True), ("F", False), ("C", False), ("G", False)], 76, None, "arp"),
    "lofi_soft": ([("D", True), ("G", False), ("C", False), ("A", True)], 82, "lofi", "quarters"),
    "playful": ([("C", False), ("F", False), ("G", False), ("C", False)], 124, "bouncy", "staccato"),
}


def synth_music(preset: str, duration: float) -> np.ndarray:
    prog, bpm, drums, arp = PRESETS[preset]
    beat = 60 / bpm
    bar = beat * 4
    n = int((duration + 0.5) * SR)
    pad = np.zeros(n)
    lead = np.zeros(n)
    perc = np.zeros(n)
    t0, k = 0.0, 0
    while t0 < duration + bar:
        root, minor = prog[k % len(prog)]
        ch = chord(root, minor, 3)
        seg = _pad(ch, bar + 0.4, bright=0.45 if preset != "ambient_pad" else 0.2)
        _place(pad, seg, t0, 0.55)
        _place(lead, _pluck(ch[0] / 2, bar, decay=1.2, harm=0.1), t0, 0.5)  # bajo
        if arp:
            notes = [ch[0] * 2, ch[1] * 2, ch[2] * 2, ch[1] * 2]
            if arp == "eighths":
                for b in range(8):
                    _place(lead, _pluck(notes[b % 4], beat / 2, 7.0), t0 + b * beat / 2, 0.16)
            elif arp == "quarters":
                for b in range(4):
                    _place(lead, _pluck(notes[b % 4], beat, 4.0), t0 + b * beat, 0.18)
            elif arp == "arp":
                for b in range(8):
                    _place(lead, _pluck(notes[b % 4], beat * 1.5, 2.2, 0.15), t0 + b * beat / 2, 0.14)
            elif arp == "staccato":
                for b in range(8):
                    if b % 3 != 2:
                        _place(lead, _pluck(notes[(b * 3) % 4] * 2, 0.12, 18.0, 0.5), t0 + b * beat / 2, 0.2)
        if drums:
            for b in range(4):
                tb = t0 + b * beat
                if drums in ("four", "drive", "bouncy") or (drums == "lofi" and b in (0, 2)):
                    _place(perc, _kick(), tb, 0.8 if drums != "lofi" else 0.6)
                if b in (1, 3) and drums in ("four", "drive", "lofi"):
                    _place(perc, _snare(), tb, 0.35)
                _place(perc, _hat(seed=b), tb + beat / 2, 0.5)
                if drums in ("drive", "bouncy"):
                    _place(perc, _hat(seed=b + 9), tb, 0.3)
        t0 += bar
        k += 1
    pad = _lowpass(pad, 1800 if preset != "ambient_pad" else 900)
    mix = pad + lead + perc
    mix = mix[: int(duration * SR)]
    mix *= _env(len(mix), 1.0, 2.0)
    peak = np.max(np.abs(mix)) or 1.0
    return mix / peak * 0.7


def synth_sfx(kind: str) -> np.ndarray:
    rng = np.random.default_rng(7)
    if kind == "whoosh":
        d = 0.45
        n = int(d * SR)
        t = np.arange(n) / SR
        noise = rng.standard_normal(n)
        # barrido: mezcla de ruido suavizado con distintas ventanas
        x = np.convolve(noise, np.ones(18) / 18, mode="same") * np.sin(np.pi * t / d) ** 2
        return x / (np.max(np.abs(x)) or 1) * 0.8
    if kind == "hit":
        d = 0.6
        t = np.arange(int(d * SR)) / SR
        x = np.sin(2 * np.pi * (55 + 40 * np.exp(-20 * t)) * t) * np.exp(-6 * t)
        x[: int(0.01 * SR)] += rng.standard_normal(int(0.01 * SR)) * 0.4
        return x / np.max(np.abs(x)) * 0.9
    if kind == "ding":
        d = 0.9
        t = np.arange(int(d * SR)) / SR
        x = (np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-5 * t)
        return x / np.max(np.abs(x)) * 0.6
    if kind == "boing":
        d = 0.55
        t = np.arange(int(d * SR)) / SR
        f = 220 + 260 * (1 - np.exp(-8 * t)) + 40 * np.sin(2 * np.pi * 14 * t) * np.exp(-4 * t)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-4.5 * t)
        return x / np.max(np.abs(x)) * 0.7
    if kind == "pop":
        d = 0.12
        t = np.arange(int(d * SR)) / SR
        x = np.sin(2 * np.pi * (500 + 900 * t / d) * t) * np.exp(-30 * t)
        return x / np.max(np.abs(x)) * 0.7
    raise ValueError(kind)


def write_wav(x: np.ndarray, path: Path) -> None:
    st = np.clip(np.stack([x, x], axis=1), -1, 1)
    data = (st * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(data.tobytes())


def music_file(preset: str, duration: float) -> Path | None:
    """Ruta a la pista para un preset ('none', preset sintético o 'library:<fichero>')."""
    s = get_settings()
    if not preset or preset == "none":
        return None
    if preset.startswith("library:"):
        name = Path(preset.split(":", 1)[1]).name  # sin rutas
        p = s.library_dir / "music" / name
        return p if p.exists() else None
    if preset not in PRESETS:
        return None
    d = int(np.ceil(duration)) + 1
    p = s.cache_dir / "audio" / f"music_{preset}_{d}.wav"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp.wav")
        write_wav(synth_music(preset, d), tmp)
        tmp.replace(p)
    return p


def sfx_file(kind: str) -> Path:
    s = get_settings()
    p = s.cache_dir / "audio" / f"sfx_{kind}.wav"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        write_wav(synth_sfx(kind), p)
    return p
