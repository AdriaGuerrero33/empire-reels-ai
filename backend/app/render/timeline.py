"""Línea de tiempo de salida derivada de un plan.

El plan guarda TODO en tiempo de la fuente (segmentos, planos, anclas de rótulos y
efectos). Así se puede recortar o reordenar en el editor sin desincronizar nada:
la línea de salida y los subtítulos se recalculan siempre desde aquí.
"""
from __future__ import annotations

import math

FPS = 30


def q(t: float, fps: int = FPS) -> float:
    """Redondea a la rejilla de fotogramas."""
    return round(round(t * fps) / fps, 6)


def snap_boundary(t: float, words: list[dict], side: str, pad: float = 0.06) -> float:
    """Si t cae dentro de una palabra, lo mueve al borde para no cortarla."""
    for w in words:
        if w["start"] < t < w["end"]:
            if side == "start":
                return max(0.0, w["start"] - pad) if (t - w["start"]) < (w["end"] - t) else w["end"] + 0.01
            return w["end"] + pad if (w["end"] - t) < (t - w["start"]) else max(0.0, w["start"] - 0.01)
        if w["start"] > t + 1:
            break
    return t


def normalize_plan(plan: dict, words: list[dict], src_duration: float) -> list[str]:
    """Sanea un plan (tras edición manual): límites, cuantización, planos contiguos.

    Devuelve avisos. Modifica el plan en sitio.
    """
    warns = []
    fps = plan.get("format", {}).get("fps", FPS)
    segs = []
    for seg in plan.get("segments", []):
        a = max(0.0, float(seg.get("src_start", 0)))
        b = min(src_duration, float(seg.get("src_end", 0)))
        a = snap_boundary(a, words, "start")
        b = snap_boundary(b, words, "end")
        a, b = q(a, fps), q(min(b, src_duration), fps)
        if b - a < 2 / fps:
            warns.append(f"Segmento {seg.get('id')} descartado por duración nula.")
            continue
        seg["src_start"], seg["src_end"] = a, b
        shots = sorted(seg.get("shots") or [], key=lambda s: s.get("src_start", 0))
        fixed = []
        cur = a
        for sh in shots:
            s0 = max(cur, q(float(sh.get("src_start", cur)), fps))
            s1 = min(b, q(float(sh.get("src_end", b)), fps))
            if s0 > cur + 1e-6:  # hueco entre planos: lo cubre un plano neutro
                fixed.append(_neutral_shot(cur, s0, fixed[-1] if fixed else sh))
            if s1 - s0 >= 1 / fps:
                sh = dict(sh)
                sh["src_start"], sh["src_end"] = s0, s1
                fixed.append(sh)
                cur = s1
        if b - cur >= 1 / fps:
            fixed.append(_neutral_shot(cur, b, fixed[-1] if fixed else {}))
        elif fixed:
            fixed[-1]["src_end"] = b
        seg["shots"] = fixed
        segs.append(seg)
    plan["segments"] = segs
    ids = {s["id"] for s in segs}
    plan["transitions"] = [t for t in plan.get("transitions", []) if t.get("after") in ids]
    return warns


def _neutral_shot(a: float, b: float, like: dict) -> dict:
    return {"src_start": a, "src_end": b, "zoom": 1.0, "push": 0.0,
            "cx": like.get("cx", 0.5), "cy": like.get("cy", 0.42), "pan": None, "broll": None, "card": None}


def build(plan: dict, words: list[dict]) -> dict:
    """Calcula tiempos de salida de segmentos, planos y palabras."""
    fps = plan.get("format", {}).get("fps", FPS)
    trans = {t["after"]: t for t in plan.get("transitions", []) if t.get("type", "cut") != "cut"}
    out_segments, out_shots = [], []
    t = 0.0
    segs = plan.get("segments", [])
    for k, seg in enumerate(segs):
        d = q(seg["src_end"] - seg["src_start"], fps)
        if k > 0:
            prev = segs[k - 1]
            tr = trans.get(prev["id"])
            if tr:
                td = min(float(tr.get("dur", 0.3)), d / 2, out_segments[-1]["dur"] / 2)
                td = q(td, fps)
                t = q(t - td, fps)
                out_segments[-1]["trans_out"] = {"type": tr.get("type", "fade"), "dur": td}
        o = {"id": seg["id"], "src_start": seg["src_start"], "src_end": seg["src_end"],
             "out_start": t, "out_end": q(t + d, fps), "dur": d, "index": k, "trans_out": None}
        out_segments.append(o)
        for sh in seg.get("shots", []):
            out_shots.append({**sh, "seg": k, "out_start": q(t + sh["src_start"] - seg["src_start"], fps),
                              "out_end": q(t + sh["src_end"] - seg["src_start"], fps)})
        t = q(t + d, fps)
    duration = t
    overrides = {int(k): v for k, v in (plan.get("subtitle_overrides") or {}).items()}
    emph = set(plan.get("emphasis") or [])
    out_words = []
    for o in out_segments:
        for w in words:
            if w["end"] <= o["src_start"] or w["start"] >= o["src_end"]:
                continue
            ws, we = max(w["start"], o["src_start"]), min(w["end"], o["src_end"])
            if we - ws < 0.5 * (w["end"] - w["start"]):
                continue  # palabra mayoritariamente fuera del segmento (borde)
            text = overrides.get(w["i"], w["text"])
            if not text or not str(text).strip():
                continue
            out_words.append({"text": str(text).strip(), "start": round(o["out_start"] + ws - o["src_start"], 3),
                              "end": round(o["out_start"] + we - o["src_start"], 3), "src_i": w["i"],
                              "emph": w["i"] in emph, "seg": o["index"], "filler": w.get("filler", False)})
    out_words.sort(key=lambda w: w["start"])
    return {"segments": out_segments, "shots": out_shots, "words": out_words, "duration": duration, "fps": fps}


def map_src(tl: dict, t: float) -> float | None:
    """Tiempo de fuente -> tiempo de salida (None si ese instante no está en el montaje)."""
    for o in tl["segments"]:
        if o["src_start"] - 1e-6 <= t <= o["src_end"] + 1e-6:
            return round(o["out_start"] + t - o["src_start"], 3)
    return None


def resolve_anchor(tl: dict, item: dict) -> tuple[float, float] | None:
    """Convierte el ancla de un rótulo/efecto a (inicio, fin) de salida."""
    dur = float(item.get("dur", 2.0))
    anchor = item.get("anchor", "src")
    if anchor == "begin":
        a = float(item.get("offset", 0.0))
    elif anchor == "end":
        a = tl["duration"] - dur - float(item.get("offset", 0.0))
    else:
        a = map_src(tl, float(item.get("src", 0.0)))
        if a is None:
            return None
    a = max(0.0, a)
    b = min(tl["duration"], a + dur)
    if b - a < 0.2:
        return None
    return a, b


def frames(t: float, fps: int = FPS) -> int:
    return int(math.floor(t * fps + 1e-6))
