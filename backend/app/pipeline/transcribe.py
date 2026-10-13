"""Transcripción con faster-whisper y marcas de tiempo por palabra, con caché por hash."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from ..config import get_settings

_model_lock = threading.Lock()
_models: dict[tuple, object] = {}

# Muletillas por idioma (se marcan, no se borran del texto: la decisión es del plan).
FILLERS = {
    "es": {"eh", "ehh", "em", "emm", "mm", "mmm", "este", "o sea", "bueno", "pues", "vale", "en plan",
           "digamos", "osea", "ah", "uh", "um"},
    "ca": {"eh", "em", "mm", "doncs", "bé", "o sigui", "vull dir", "saps", "ah", "um"},
    "en": {"uh", "um", "uhm", "er", "erm", "ah", "like", "you know", "i mean", "so", "basically",
           "actually", "mm"},
}
# Solo cuentan como muletilla en estas posiciones ambiguas si van aisladas por pausas.
AMBIGUOUS = {"este", "bueno", "pues", "vale", "like", "so", "actually", "basically", "doncs", "bé"}


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _resolve_device() -> tuple[str, str]:
    s = get_settings()
    device = s.whisper_device
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    compute = s.whisper_compute_type
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def get_model(name: str):
    device, compute = _resolve_device()
    key = (name, device, compute)
    with _model_lock:
        if key not in _models:
            from faster_whisper import WhisperModel
            import os
            _models[key] = WhisperModel(name, device=device, compute_type=compute,
                                        cpu_threads=max(1, (os.cpu_count() or 2)))
        return _models[key]


def _norm(w: str) -> str:
    return re.sub(r"[^\wàáèéíïòóúüçñ' ]", "", w.lower()).strip()


def mark_fillers(words: list[dict], lang: str) -> None:
    fillers = FILLERS.get(lang, FILLERS["es"])
    n = len(words)
    for i, w in enumerate(words):
        t = _norm(w["text"])
        two = t + " " + _norm(words[i + 1]["text"]) if i + 1 < n else ""
        is_f = False
        if two in fillers:
            is_f = True
            words[i + 1]["filler"] = True
        elif t in fillers:
            if t in AMBIGUOUS:
                gap_before = w["start"] - words[i - 1]["end"] if i > 0 else 1.0
                gap_after = words[i + 1]["start"] - w["end"] if i + 1 < n else 1.0
                ends_clause = w["text"].rstrip().endswith((",", "..."))
                is_f = (gap_before > 0.25 and gap_after > 0.25) or (gap_before > 0.25 and ends_clause)
            else:
                is_f = True
        w["filler"] = bool(w.get("filler") or is_f)


def transcribe(audio: Path, language: str, on_progress=None) -> dict:
    """Devuelve {language, duration, segments:[{start,end,text,words:[...]}], words:[...]}.

    Se cachea por (hash de audio, modelo, idioma): reanálisis y regeneraciones no
    vuelven a transcribir.
    """
    s = get_settings()
    digest = file_hash(audio)
    cache = s.cache_dir / "transcripts" / f"{digest[:24]}_{s.whisper_model}_{language}.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        data["cached"] = True
        return data

    model = get_model(s.whisper_model)
    t0 = time.perf_counter()
    segments_iter, info = model.transcribe(
        str(audio), language=language or None, word_timestamps=True, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300}, beam_size=5, condition_on_previous_text=False,
    )
    total = info.duration or 1.0
    segments, words = [], []
    for seg in segments_iter:
        sw = []
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            item = {"text": text, "start": round(float(w.start), 3), "end": round(float(w.end), 3),
                    "prob": round(float(w.probability), 3)}
            if item["end"] <= item["start"]:
                item["end"] = round(item["start"] + 0.05, 3)
            sw.append(item)
        if not sw:
            continue
        words.extend(sw)
        segments.append({"start": sw[0]["start"], "end": sw[-1]["end"], "text": seg.text.strip(),
                         "word_range": [len(words) - len(sw), len(words)]})
        if on_progress:
            on_progress(min(0.99, seg.end / total))
    # Monotonía estricta (whisper a veces solapa palabras contiguas).
    for i in range(1, len(words)):
        if words[i]["start"] < words[i - 1]["end"]:
            mid = round((words[i]["start"] + words[i - 1]["end"]) / 2, 3)
            words[i - 1]["end"] = max(words[i - 1]["start"] + 0.02, mid)
            words[i]["start"] = max(words[i]["start"], words[i - 1]["end"])
            words[i]["end"] = max(words[i]["end"], words[i]["start"] + 0.02)
    mark_fillers(words, language)
    for i, w in enumerate(words):
        w["i"] = i
    data = {"language": info.language, "language_prob": round(float(info.language_probability), 3),
            "duration": round(float(info.duration), 3), "model": s.whisper_model,
            "segments": segments, "words": words, "elapsed_s": round(time.perf_counter() - t0, 2)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    data["cached"] = False
    return data
