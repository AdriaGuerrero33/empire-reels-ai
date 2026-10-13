"""Análisis editorial: frases, rasgos, puntuaciones, cambios de tema y clips candidatos."""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from .audio_analysis import span_energy
from .lexicon import LEADING_CONNECTORS, MARKERS, NUMBER_WORDS, STOP, lang_key

END_PUNCT = (".", "?", "!", "…")
CATEGORIES = ["question", "surprise", "tip", "anecdote", "explanation", "cta", "problem", "solution",
              "benefit", "emphatic", "closure", "humor", "number"]


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def build_sentences(words: list[dict], pause_split: float = 0.7, max_words: int = 32) -> list[dict]:
    """Agrupa palabras en frases por puntuación, pausas largas o longitud máxima."""
    sents, cur = [], []

    def flush():
        if cur:
            sents.append(list(cur))
            cur.clear()

    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 9.0
        txt = w["text"]
        if txt.endswith(END_PUNCT):
            flush()
        elif gap >= pause_split and len(cur) >= 3:
            flush()
        elif len(cur) >= max_words and (txt.endswith((",", ";", ":")) or gap > 0.2):
            flush()
        elif len(cur) >= max_words + 12:
            flush()
    flush()
    out = []
    for k, sw in enumerate(sents):
        out.append({
            "id": k, "w0": sw[0]["i"], "w1": sw[-1]["i"] + 1,
            "start": sw[0]["start"], "end": sw[-1]["end"],
            "text": _clean(" ".join(w["text"] for w in sw)),
        })
    for k, s in enumerate(out):
        s["gap_before"] = round(s["start"] - out[k - 1]["end"], 3) if k else round(s["start"], 3)
        s["gap_after"] = round(out[k + 1]["start"] - s["end"], 3) if k + 1 < len(out) else 1.0
    return out


def _has(text_l: str, phrases: list[str]) -> int:
    n = 0
    for p in phrases:
        if p.startswith("¿"):
            n += text_l.count("¿")
            continue
        if re.search(r"(?<![\wàáèéíïòóúüçñ])" + re.escape(p), text_l):
            n += 1
    return n


def content_words(text: str, lang: str) -> list[str]:
    stop = STOP[lang_key(lang)]
    toks = re.findall(r"[a-zàáèéíïòóúüçñ0-9'’-]+", text.lower())
    return [t for t in toks if len(t) > 3 and t not in stop and not t.isdigit()]


def sentence_features(s: dict, words: list[dict], lang: str, curve: dict, voiced_mean: float) -> dict:
    lk = lang_key(lang)
    sw = words[s["w0"]:s["w1"]]
    text = s["text"]
    tl = " " + text.lower() + " "
    n = len(sw)
    dur = max(0.1, s["end"] - s["start"])
    f: dict = {}
    for cat in ["question", "surprise", "tip", "anecdote", "explanation", "cta", "problem", "solution",
                "benefit", "emphatic", "closure", "humor"]:
        f[cat] = _has(tl, MARKERS[cat][lk])
    if text.rstrip().endswith("?"):
        f["question"] += 2
    if "!" in text:
        f["emphatic"] += 1
    f["number"] = len(re.findall(r"\d", text)) and 1 + len(re.findall(r"\d+[%€$]?|%|€|\$", text))
    f["number"] += _has(tl, NUMBER_WORDS[lk])
    first = re.sub(r"[^\wàáèéíïòóúüçñ' ]", "", sw[0]["text"].lower()) if sw else ""
    first2 = " ".join(re.sub(r"[^\wàáèéíïòóúüçñ' ]", "", w["text"].lower()) for w in sw[:2])
    lead = LEADING_CONNECTORS[lk]
    f["leading_connector"] = first in lead or first2 in lead
    f["words"] = n
    f["duration"] = round(dur, 2)
    f["rate_wps"] = round(n / dur, 2)
    f["confidence"] = round(float(np.mean([w.get("prob", 0.9) for w in sw])) if sw else 0.0, 3)
    f["filler_ratio"] = round(sum(1 for w in sw if w.get("filler")) / max(1, n), 3)
    f["energy_db"] = round(span_energy(curve, s["start"], s["end"]), 1)
    f["energy_rel"] = round(f["energy_db"] - voiced_mean, 1)
    f["ends_clean"] = text.rstrip().endswith(END_PUNCT)
    return f


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def score_sentence(f: dict) -> dict:
    """Puntuaciones 0-1 a partir de rasgos estructurales, prosódicos y retóricos."""
    n = f["words"]
    # Claridad: confianza del reconocimiento, pocas muletillas, ritmo inteligible.
    rate_pen = 0.0 if 1.6 <= f["rate_wps"] <= 4.2 else min(1.0, abs(f["rate_wps"] - 2.9) / 3)
    clarity = max(0.0, min(1.0, 0.55 * f["confidence"] + 0.45 * (1 - 3 * f["filler_ratio"]) - 0.3 * rate_pen))
    # Autonomía: se entiende sin contexto previo.
    autonomy = 1.0
    if f["leading_connector"]:
        autonomy -= 0.45
    if not f["ends_clean"]:
        autonomy -= 0.15
    if n < 4:
        autonomy -= 0.35
    elif n > 34:
        autonomy -= 0.2
    autonomy = max(0.0, autonomy)
    rhet = (0.9 * min(f["question"], 2) + 0.8 * min(f["surprise"], 2) + 0.5 * min(f["number"], 2)
            + 0.5 * min(f["emphatic"], 2) + 0.4 * min(f["problem"], 2) + 0.3 * min(f["benefit"], 2))
    energy = max(-1.0, min(1.0, f["energy_rel"] / 6))
    length_fit = 1.0 if 5 <= n <= 20 else (0.6 if n <= 28 else 0.3)
    hook = _sig(-2.2 + 0.85 * rhet + 1.4 * autonomy + 0.8 * energy + 0.8 * length_fit + 0.6 * clarity)
    value = _sig(-1.6 + 0.7 * min(f["tip"], 2) + 0.6 * min(f["explanation"], 2) + 0.5 * min(f["number"], 2)
                 + 0.5 * min(f["solution"], 2) + 0.4 * min(f["benefit"], 2) + 1.0 * clarity + 0.4 * autonomy)
    narrative = _sig(-1.8 + 1.0 * min(f["anecdote"], 2) + 0.5 * min(f["surprise"], 2) + 0.4 * min(f["emphatic"], 1)
                     + 0.6 * clarity + 0.3 * energy)
    retention = 0.45 * hook + 0.3 * value + 0.25 * clarity
    return {k: round(v, 3) for k, v in
            {"hook": hook, "clarity": clarity, "autonomy": autonomy, "value": value,
             "narrative": narrative, "retention": retention, "energy": (energy + 1) / 2}.items()}


def labels_from(f: dict) -> list[str]:
    return [c for c in CATEGORIES if f.get(c)]


def topic_boundaries(sents: list[dict], lang: str, win: int = 3) -> list[int]:
    """Índices de frase donde empieza un tema nuevo (caída de similitud léxica o pausa larga)."""
    if len(sents) < 2 * win + 1:
        return []
    bags = [Counter(content_words(s["text"], lang)) for s in sents]

    def cos(a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        inter = set(a) & set(b)
        num = sum(a[t] * b[t] for t in inter)
        den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
        return num / den if den else 0.0

    sims = []
    for k in range(win, len(sents) - win + 1):
        left = sum(bags[k - win:k], Counter())
        right = sum(bags[k:k + win], Counter())
        sims.append((k, cos(left, right)))
    vals = [v for _, v in sims]
    mean = float(np.mean(vals)) if vals else 0.0
    std = float(np.std(vals)) if vals else 0.0
    out = []
    for idx, (k, v) in enumerate(sims):
        lo = idx == 0 or v <= sims[idx - 1][1]
        hi = idx == len(sims) - 1 or v <= sims[idx + 1][1]
        if lo and hi and v < mean - 0.5 * std:
            out.append(k)
        elif sents[k]["gap_before"] > 1.5 and k not in out:
            out.append(k)
    return sorted(set(out))


def broll_keywords(text: str, lang: str, k: int = 3) -> list[str]:
    cw = content_words(text, lang)
    seen, out = set(), []
    for w in sorted(cw, key=lambda t: -len(t)):
        root = w[:6]
        if root in seen:
            continue
        seen.add(root)
        out.append(w)
        if len(out) >= k:
            break
    return out


def analyze_text(words: list[dict], lang: str, curve: dict, voiced_mean: float) -> dict:
    sents = build_sentences(words)
    for s in sents:
        f = sentence_features(s, words, lang, curve, voiced_mean)
        s["features"] = f
        s["scores"] = score_sentence(f)
        s["labels"] = labels_from(f)
        s["keywords"] = broll_keywords(s["text"], lang)
    bounds = topic_boundaries(sents, lang)
    topic = 0
    for i, s in enumerate(sents):
        if i in bounds:
            topic += 1
        s["topic"] = topic
    return {"sentences": sents, "topic_starts": bounds, "n_topics": topic + 1}


def window_duration(sents: list[dict], i: int, j: int, max_gap: float = 0.4) -> float:
    """Duración estimada de las frases i..j con las pausas internas recortadas a max_gap."""
    d = 0.0
    for k in range(i, j + 1):
        d += sents[k]["end"] - sents[k]["start"]
        if k > i:
            d += min(sents[k]["gap_before"], max_gap)
    return d


def candidate_windows(sents: list[dict], target: float, weights: dict, max_gap: float = 0.4,
                      tol: tuple[float, float] = (0.65, 1.12)) -> list[dict]:
    """Ventanas contiguas de frases cuya duración encaja con el objetivo, puntuadas por estilo."""
    out = []
    n = len(sents)
    for i in range(n):
        for j in range(i, n):
            d = window_duration(sents, i, j, max_gap)
            if d > target * tol[1]:
                break
            if d < target * tol[0]:
                continue
            seg = sents[i:j + 1]
            sc = [s["scores"] for s in seg]
            mean = {k: float(np.mean([x[k] for x in sc])) for k in sc[0]}
            label_counts = Counter(l for s in seg for l in s["labels"])
            topics = len(set(s["topic"] for s in seg))
            first, last = seg[0], seg[-1]
            score = (weights.get("hook", 0.3) * first["scores"]["hook"]
                     + weights.get("clarity", 0.2) * mean["clarity"]
                     + weights.get("value", 0.2) * mean["value"]
                     + weights.get("narrative", 0.0) * mean["narrative"]
                     + weights.get("retention", 0.2) * mean["retention"]
                     + weights.get("energy", 0.0) * mean["energy"]
                     + 0.15 * first["scores"]["autonomy"]
                     + 0.12 * (1.0 if last["features"]["ends_clean"] else 0.0)
                     + 0.08 * min(1, last["features"]["closure"] + last["features"]["cta"])
                     - 0.10 * max(0, topics - 1)
                     - 0.05 * abs(d - target) / max(1.0, target))
            for lab, w in (weights.get("labels") or {}).items():
                score += w * min(2, label_counts.get(lab, 0)) / 2
            out.append({"i": i, "j": j, "start": first["start"], "end": last["end"], "duration": round(d, 2),
                        "score": round(score, 4), "topics": topics, "labels": dict(label_counts)})
    out.sort(key=lambda c: -c["score"])
    return out


def overlap(a: dict, b: dict) -> float:
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    return inter / max(0.01, min(a["end"] - a["start"], b["end"] - b["start"]))
