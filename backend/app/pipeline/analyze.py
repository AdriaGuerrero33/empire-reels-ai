"""Análisis completo del vídeo original (se hace UNA vez y lo comparten las 10 versiones)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .. import media as M
from . import audio_analysis, llm, semantic, transcribe, visual

Stage = Callable[[float, str], None]


def project_paths(pdir: Path) -> dict[str, Path]:
    return {"audio": pdir / "audio.wav", "proxy": pdir / "proxy.mp4", "analysis": pdir / "analysis.json"}


def run_analysis(pdir: Path, source: Path, info: dict, language: str, on_stage: Stage) -> tuple[dict, list[dict]]:
    """Devuelve (analysis, metrics). Las métricas son mediciones reales por paso."""
    paths = project_paths(pdir)
    metrics: list[dict] = []
    dur = info["duration"]

    def metric(kind: str, t0: float, cpu: float = 0.0, **extra):
        metrics.append({"kind": kind, "wall_s": round(time.perf_counter() - t0, 3), "cpu_s": round(cpu, 3),
                        "media_s": dur, "extra": extra})

    analysis: dict = {"version": 1, "language": language, "duration": dur, "media": info}

    # 1. Audio
    words: list[dict] = []
    curve = {"hop": 0.05, "db": []}
    if info.get("has_audio"):
        on_stage(0.02, "Extrayendo audio")
        t0 = time.perf_counter()
        r = M.extract_audio(source, paths["audio"])
        metric("extract_audio", t0, r.cpu_s)

        on_stage(0.05, "Transcribiendo (faster-whisper)")
        t0 = time.perf_counter()
        tr = transcribe.transcribe(paths["audio"], language,
                                   on_progress=lambda p: on_stage(0.05 + 0.5 * p, f"Transcribiendo {int(p * 100)} %"))
        metric("transcribe", t0, model=tr.get("model"), cached=tr.get("cached"), words=len(tr["words"]))
        words = tr["words"]
        analysis["transcript"] = tr
        if tr.get("language") and tr["language"] != language:
            analysis.setdefault("warnings", []).append(
                f"Whisper detecta idioma «{tr['language']}» (se pidió «{language}»).")

        on_stage(0.56, "Detectando silencios y energía de voz")
        t0 = time.perf_counter()
        analysis["silences"] = M.detect_silences(paths["audio"])
        curve = audio_analysis.energy_curve(paths["audio"])
        analysis["energy"] = curve
        analysis["loudness"] = audio_analysis.loudness_stats(curve)
        metric("audio_analysis", t0)
    else:
        analysis["transcript"] = {"words": [], "segments": [], "language": language}
        analysis["silences"] = []
        analysis["energy"] = curve
        analysis["loudness"] = {}
        analysis.setdefault("warnings", []).append("El vídeo no tiene pista de audio.")

    # 2. Proxy de baja resolución (análisis visual y previsualización)
    on_stage(0.6, "Creando proxy de previsualización")
    t0 = time.perf_counter()
    r = M.make_proxy(source, paths["proxy"], on_progress=lambda p: on_stage(0.6 + 0.1 * p, "Creando proxy"),
                     duration=dur)
    metric("proxy", t0, r.cpu_s)

    # 3. Escenas
    on_stage(0.71, "Detectando cambios de escena")
    t0 = time.perf_counter()
    try:
        analysis["scenes"] = visual.detect_scenes(paths["proxy"])
    except Exception as e:  # no bloquea el resto del análisis
        analysis["scenes"] = []
        analysis.setdefault("warnings", []).append(f"Detección de escenas fallida: {e}")
    metric("scenes", t0, n=len(analysis["scenes"]))

    # 4. Caras
    on_stage(0.78, "Detectando y siguiendo caras")
    t0 = time.perf_counter()
    analysis["faces"] = visual.track_faces(paths["proxy"],
                                           on_progress=lambda p: on_stage(0.78 + 0.12 * p, "Siguiendo caras"))
    metric("faces", t0, face_ratio=analysis["faces"].get("face_ratio"))

    # 5. Análisis editorial
    on_stage(0.91, "Analizando contenido (frases, ganchos, temas)")
    t0 = time.perf_counter()
    voiced = analysis["loudness"].get("voiced_mean_db", -25.0) if analysis["loudness"] else -25.0
    sem = semantic.analyze_text(words, language, curve, voiced) if words else \
        {"sentences": [], "topic_starts": [], "n_topics": 0}
    metric("semantic", t0, sentences=len(sem["sentences"]))
    lr = llm.LLMResult()
    if sem["sentences"]:
        status = llm.provider_status()
        if status["provider"] != "heuristic":
            on_stage(0.93, f"Refinando con LLM ({status['provider']})")
            t0 = time.perf_counter()
            lr = llm.refine_sentences(sem["sentences"], language)
            n = llm.merge_llm(sem["sentences"], lr)
            metrics.append({"kind": "llm", "wall_s": lr.wall_s, "cpu_s": 0.0, "media_s": dur,
                            "cost_eur": lr.cost_eur, "extra": {"provider": lr.provider, "model": lr.model,
                                                               "tokens_in": lr.tokens_in, "tokens_out": lr.tokens_out,
                                                               "sentences": n, "error": lr.error}})
            if lr.error:
                analysis.setdefault("warnings", []).append(f"LLM: {lr.error}")
    analysis.update(sem)
    analysis["llm"] = {"provider": lr.provider, "model": lr.model, "tokens_in": lr.tokens_in,
                       "tokens_out": lr.tokens_out, "cost_eur": lr.cost_eur, "error": lr.error}
    analysis["highlights"] = highlights(sem["sentences"])
    on_stage(0.98, "Guardando análisis")
    save_analysis(pdir, analysis)
    return analysis, metrics


def highlights(sents: list[dict], k: int = 8) -> list[dict]:
    """Momentos destacados para la pantalla de análisis."""
    out = []
    for key, label in (("hook", "Gancho"), ("value", "Consejo / valor"), ("narrative", "Momento narrativo")):
        for s in sorted(sents, key=lambda x: -x["scores"][key])[:3]:
            if s["scores"][key] < 0.45:
                continue
            out.append({"kind": label, "sentence": s["id"], "start": s["start"], "end": s["end"],
                        "text": s["text"], "score": s["scores"][key], "labels": s["labels"]})
    for s in sents:
        if "question" in s["labels"] and s["scores"]["autonomy"] >= 0.5:
            out.append({"kind": "Pregunta", "sentence": s["id"], "start": s["start"], "end": s["end"],
                        "text": s["text"], "score": s["scores"]["hook"], "labels": s["labels"]})
        if "cta" in s["labels"]:
            out.append({"kind": "Llamada a la acción", "sentence": s["id"], "start": s["start"], "end": s["end"],
                        "text": s["text"], "score": s["scores"]["retention"], "labels": s["labels"]})
    seen, uniq = set(), []
    for h in sorted(out, key=lambda h: -h["score"]):
        if (h["sentence"], h["kind"]) in seen:
            continue
        seen.add((h["sentence"], h["kind"]))
        uniq.append(h)
    return uniq[: k * 2]


def save_analysis(pdir: Path, analysis: dict) -> None:
    p = project_paths(pdir)["analysis"]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def load_analysis(pdir: Path) -> dict | None:
    p = project_paths(pdir)["analysis"]
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
