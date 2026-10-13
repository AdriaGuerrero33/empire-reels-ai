"""Planificador editorial: análisis + estilo -> plan de edición JSON (EDL serializada).

Reglas que se respetan siempre:
- Los cortes caen en pausas entre palabras (nunca en mitad de una palabra).
- Los textos en pantalla salen literalmente de la transcripción (o de la marca del
  usuario, p. ej. su CTA): no se inventan afirmaciones.
- El gancho puede adelantarse, pero el resto conserva el orden original.
"""
from __future__ import annotations

import re

from ..render.timeline import FPS, build, normalize_plan, q
from . import broll as broll_mod
from .semantic import candidate_windows, overlap, window_duration
from .styles import ALT_MUSIC, ALT_SUBTITLES, FORMATS, STYLES, STYLE_ORDER
from .visual import face_center

STAGE_LABELS = {
    "es": {"problem": "EL PROBLEMA", "solution": "LA SOLUCIÓN", "benefit": "EL BENEFICIO", "cta": "SIGUIENTE PASO"},
    "ca": {"problem": "EL PROBLEMA", "solution": "LA SOLUCIÓ", "benefit": "EL BENEFICI", "cta": "SEGÜENT PAS"},
    "en": {"problem": "THE PROBLEM", "solution": "THE SOLUTION", "benefit": "THE BENEFIT", "cta": "NEXT STEP"},
}


def fmt_time(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def short_phrase(text: str, max_words: int = 8) -> str:
    """Recorte extractivo: la cláusula más informativa con <= max_words palabras."""
    text = re.sub(r"\s+", " ", text).strip()
    parts = [p.strip(" ,;:") for p in re.split(r"[,;:]| y | pero | and | but | i | però ", text) if p.strip(" ,;:")]
    parts = parts or [text]
    best = max(parts, key=lambda p: (min(len(p.split()), max_words) - 0.3 * max(0, len(p.split()) - max_words),
                                     sum(ch.isdigit() for ch in p)))
    words = best.split()
    out = " ".join(words[:max_words])
    return out.rstrip(".,;:") + ("…" if len(words) > max_words else "")


def speech_bounds(sents: list[dict]) -> float:
    return sum(s["end"] - s["start"] for s in sents)


# ---------------------------------------------------------------------------
# Selección de frases
# ---------------------------------------------------------------------------

def choose_window(style: dict, sents: list[dict], target: float, used: list[dict], variant: int) -> tuple[dict, list[str]]:
    notes = []
    cands = candidate_windows(sents, target, style["weights"], max_gap=style["max_gap"])
    if not cands:
        whole = {"i": 0, "j": len(sents) - 1, "start": sents[0]["start"], "end": sents[-1]["end"],
                 "duration": round(window_duration(sents, 0, len(sents) - 1, style["max_gap"]), 2),
                 "score": 0.0, "labels": {}}
        notes.append("El material es más corto que la duración pedida: se usa todo el discurso.")
        return whole, notes
    for c in cands:
        c["adj"] = c["score"] - 0.45 * max([overlap(c, u) for u in used] or [0.0])
    cands.sort(key=lambda c: -c["adj"])
    distinct: list[dict] = []
    for c in cands:
        if all(overlap(c, d) < 0.5 for d in distinct):
            distinct.append(c)
        if len(distinct) > variant:
            break
    pick = distinct[min(variant, len(distinct) - 1)]
    if variant and len(distinct) <= variant:
        notes.append("No hay más fragmentos distintos de esta duración: variante sobre el mismo fragmento.")
    return pick, notes


def pick_hook(sents: list[dict], window_ids: list[int], target: float) -> int | None:
    first = sents[window_ids[0]]
    best, best_sc = None, first["scores"]["hook"] + 0.08
    for s in sents:
        d = s["end"] - s["start"]
        if not (1.2 <= d <= min(7.0, target * 0.35)):
            continue
        sc = s["scores"]
        if sc["hook"] > best_sc and sc["hook"] >= 0.55 and sc["autonomy"] >= 0.55 and s["features"]["ends_clean"]:
            best, best_sc = s["id"], sc["hook"]
    return best


# ---------------------------------------------------------------------------
# Segmentos (cortes en pausas y muletillas)
# ---------------------------------------------------------------------------

def segments_from_sentences(order: list[int], sents: list[dict], words: list[dict], style: dict,
                            duration: float, roles: dict[int, str]) -> tuple[list[dict], dict]:
    """Convierte frases ordenadas en segmentos de audio continuo."""
    max_gap, pad = style["max_gap"], style["pad"]
    stats = {"cuts": 0, "saved_s": 0.0, "fillers_removed": 0}
    # Agrupar frases consecutivas en la fuente para no cortar entre ellas sin motivo
    groups: list[list[int]] = []
    for sid in order:
        if groups and sid == groups[-1][-1] + 1:
            groups[-1].append(sid)
        else:
            groups.append([sid])
    segs = []
    for g in groups:
        w0, w1 = sents[g[0]]["w0"], sents[g[-1]]["w1"]
        ws = list(range(w0, w1))
        if style.get("remove_fillers"):
            kept = [i for i in ws if not words[i].get("filler")]
            if len(kept) >= max(1, len(ws) // 2):
                stats["fillers_removed"] += len(ws) - len(kept)
                ws = kept
        runs: list[list[int]] = [[ws[0]]] if ws else []
        for i in ws[1:]:
            prev = runs[-1][-1]
            gap = words[i]["start"] - words[prev]["end"]
            if i != prev + 1 or gap > max_gap:  # pausa larga o muletilla eliminada
                stats["cuts"] += 1
                stats["saved_s"] += max(0.0, gap - 2 * pad)
                runs.append([i])
            else:
                runs[-1].append(i)
        for run in runs:
            a_w, b_w = words[run[0]], words[run[-1]]
            prev_end = words[run[0] - 1]["end"] if run[0] > 0 else 0.0
            next_start = words[run[-1] + 1]["start"] if run[-1] + 1 < len(words) else duration
            pin = min(pad, max(0.0, (a_w["start"] - prev_end) / 2))
            pout = min(pad + 0.04, max(0.0, (next_start - b_w["end"]) / 2))
            a = max(0.0, a_w["start"] - pin)
            b = min(duration, b_w["end"] + pout)
            aq, bq = q(a), q(b)
            if aq < prev_end - 1e-3:
                aq = q(a + 1 / FPS / 2 + 1e-4)
            if bq > next_start + 1e-3:
                bq = q(b - 1 / FPS / 2 - 1e-4)
            if bq - aq < 0.25:
                continue
            sid = next((s for s in g if sents[s]["w0"] <= run[0] < sents[s]["w1"]), g[0])
            segs.append({"id": f"s{len(segs)}", "src_start": aq, "src_end": bq, "role": roles.get(sid, "body"),
                         "sentence_ids": sorted({s for s in g if not (sents[s]["w1"] <= run[0] or sents[s]["w0"] > run[-1])}),
                         "shots": []})
    stats["saved_s"] = round(stats["saved_s"], 2)
    return segs, stats


# ---------------------------------------------------------------------------
# Planos: escenas, zooms, reencuadre y B-roll
# ---------------------------------------------------------------------------

def _split(seg: dict, cuts: list[float]) -> None:
    pts = sorted({q(c) for c in cuts if seg["src_start"] + 0.25 < c < seg["src_end"] - 0.25})
    bounds = [seg["src_start"], *pts, seg["src_end"]]
    seg["shots"] = [{"src_start": bounds[k], "src_end": bounds[k + 1], "zoom": 1.0, "push": 0.0, "cx": 0.5,
                     "cy": 0.42, "pan": None, "broll": None, "card": None, "reason": ""}
                    for k in range(len(bounds) - 1)]


def emphasis_words(words: list[dict], ids: list[int], sents: list[dict], curve_mean: float) -> list[int]:
    """Palabras a resaltar: cifras, palabras clave de la frase y picos de energía."""
    out = []
    for sid in ids:
        s = sents[sid]
        kws = {k[:6] for k in s.get("keywords", [])}
        for i in range(s["w0"], s["w1"]):
            t = re.sub(r"[^\wàáèéíïòóúüçñ%€$]", "", words[i]["text"].lower())
            if not t or words[i].get("filler"):
                continue
            if any(ch.isdigit() for ch in t) or "%" in t or "€" in t:
                out.append(i)
            elif len(t) >= 5 and t[:6] in kws:
                out.append(i)
    # máximo ~1 de cada 5 palabras para que el énfasis signifique algo
    total = sum(sents[s]["w1"] - sents[s]["w0"] for s in ids)
    limit = max(2, total // 5)
    return sorted(set(out))[: limit]


def plan_shots(plan: dict, style: dict, sents: list[dict], words: list[dict], analysis: dict,
               lang: str, portrait: bool, cfg: dict) -> list[str]:
    notes = []
    scenes = [sc["start"] for sc in analysis.get("scenes", [])][1:]
    zoom = style["zoom"]
    mode = zoom.get("mode", "none")
    emph = set(plan["emphasis"])
    segs = plan["segments"]
    hook_seg = segs[0]["id"] if segs and segs[0]["role"] == "hook" else None
    zoom_events: list[float] = []

    # 1) Puntos de corte de plano: escenas + eventos de zoom (según el contenido)
    for seg in segs:
        cuts = [c for c in scenes if seg["src_start"] < c < seg["src_end"]]
        if mode in ("punch", "comic"):
            spacing = zoom.get("min_spacing", 3.5)
            for i in sorted(emph):
                w = words[i]
                if not (seg["src_start"] + 0.3 < w["start"] < seg["src_end"] - 0.6):
                    continue
                if mode == "comic":
                    sid = next((s["id"] for s in sents if s["w0"] <= i < s["w1"]), None)
                    f = sents[sid]["features"] if sid is not None else {}
                    if not (f.get("emphatic") or f.get("humor") or f.get("surprise") or "!" in w["text"]):
                        continue
                if zoom_events and w["start"] - zoom_events[-1] < spacing:
                    continue
                zoom_events.append(w["start"])
                end = min(seg["src_end"], w["start"] + (0.9 if mode == "comic" else 2.2))
                cuts += [w["start"] - 0.04, end]
        elif mode in ("alternate", "speaker"):
            for sid in seg["sentence_ids"]:
                st = sents[sid]["start"] - 0.05
                if seg["src_start"] + 0.4 < st < seg["src_end"] - 1.2:
                    cuts.append(st)
        _split(seg, cuts)

    # 2) Zoom por plano
    flip = False
    for seg in segs:
        for sh in seg["shots"]:
            d = sh["src_end"] - sh["src_start"]
            if mode in ("punch", "comic"):
                if any(abs(sh["src_start"] - (t - 0.04)) < 0.02 for t in zoom_events):
                    sh["zoom"] = zoom["scale"]
                    sh["reason"] = "énfasis"
            elif mode == "alternate":
                if d >= 1.0:
                    sh["zoom"] = zoom["scale"] if flip else 1.0
                    flip = not flip
                    sh["reason"] = "cambio de encuadre por frase"
            elif mode == "speaker":
                sh["zoom"] = zoom["scale"] if flip else 1.08
                flip = not flip
            elif mode == "push" and d >= 2.5:
                sh["push"] = zoom["scale"] - 1.0
    if zoom_events:
        notes.append(f"{len(zoom_events)} zooms en palabras con énfasis (cifras/palabras clave), separados ≥ "
                     f"{zoom.get('min_spacing', 3)} s.")

    # 3) Reencuadre por plano siguiendo al protagonista
    faces = analysis.get("faces", {})
    last = {"cx": 0.5, "cy": 0.42}
    n_face = 0
    for seg in segs:
        for sh in seg["shots"]:
            fc = face_center(faces, sh["src_start"], sh["src_end"]) if faces.get("samples") else None
            if fc:
                n_face += 1
                sh["cx"], sh["cy"] = round(fc["cx"], 4), round(fc["cy"], 4)
                sh["face_h"] = round(fc["h"], 4)
                if fc["spread"] > 0.05 and sh["src_end"] - sh["src_start"] >= 1.5 and \
                        abs(fc["cx_end"] - fc["cx_start"]) > 0.05:
                    sh["pan"] = [round(fc["cx_start"], 4), round(fc["cx_end"], 4)]
                last = {"cx": sh["cx"], "cy": sh["cy"]}
            else:
                sh["cx"], sh["cy"] = last["cx"], last["cy"]
    total_shots = sum(len(s["shots"]) for s in segs)
    if faces.get("samples"):
        notes.append(f"Reencuadre siguiendo la cara en {n_face}/{total_shots} planos.")

    # 4) B-roll
    bcfg = style.get("broll", {})
    if bcfg.get("enabled") and cfg.get("broll", True):
        notes += place_broll(plan, bcfg, sents, lang, portrait, hook_seg)
    return notes


def place_broll(plan: dict, bcfg: dict, sents: list[dict], lang: str, portrait: bool, hook_seg: str | None) -> list[str]:
    tl = build(plan, [])
    total = tl["duration"]
    budget = total * bcfg.get("max_ratio", 0.2)
    used_t, last_out = 0.0, -99.0
    placed, used_urls = 0, set()
    providers = broll_mod.available()
    fallback = bcfg.get("fallback", "none")
    notes = []
    for seg_o, seg in zip(tl["segments"], plan["segments"]):
        if seg["id"] == hook_seg:
            continue
        for sid in seg["sentence_ids"]:
            s = sents[sid]
            kws = s.get("keywords") or []
            if not kws and not s.get("broll_query_en"):
                continue
            if s["scores"].get("value", 0) < 0.35 and not s.get("broll_query_en"):
                continue
            a = max(seg["src_start"], s["start"] + 0.15)
            b = min(seg["src_end"], a + 3.0, s["end"])
            if b - a < 1.4:
                continue
            out_a = seg_o["out_start"] + a - seg["src_start"]
            if out_a < 2.5 or out_a - last_out < bcfg.get("min_gap", 5.0) or used_t + (b - a) > budget:
                continue
            asset = None
            if providers:
                asset = broll_mod.find(kws, lang, portrait, used_urls, s.get("broll_query_en"))
            card = None
            if not asset:
                if fallback != "card":
                    continue
                card = {"text": " ".join(k.upper() for k in kws[:2])}
            # Insertar como plano propio dentro del segmento
            new = []
            for sh in seg["shots"]:
                if sh["src_end"] <= a or sh["src_start"] >= b:
                    new.append(sh)
                    continue
                if sh["src_start"] < a:
                    new.append({**sh, "src_end": q(a)})
                new.append({**sh, "src_start": q(max(a, sh["src_start"])), "src_end": q(min(b, sh["src_end"])),
                            "zoom": 1.0, "push": 0.0, "pan": None, "broll": asset, "card": card,
                            "reason": "b-roll: " + (asset["query"] if asset else "rótulo interno")})
                if sh["src_end"] > b:
                    new.append({**sh, "src_start": q(b)})
            seg["shots"] = new
            if asset:
                used_urls.add(asset["source_url"])
            placed += 1
            used_t += b - a
            last_out = out_a
    if placed:
        notes.append(f"{placed} inserciones de apoyo visual ({'archivo con licencia' if providers else 'rótulos internos'}).")
    elif bcfg.get("enabled") and not providers:
        notes.append("B-roll sin proveedores configurados (Pexels/Pixabay): se mantiene el vídeo original.")
    return notes


# ---------------------------------------------------------------------------
# Rótulos, efectos y audio
# ---------------------------------------------------------------------------

def plan_overlays(plan: dict, style: dict, sents: list[dict], words: list[dict], order: list[int],
                  lang: str, cfg: dict) -> list[str]:
    ov, sfx, notes = [], [], []
    kinds = style.get("overlays", [])
    first = sents[order[0]]
    lk = lang if lang in STAGE_LABELS else "es"
    if "hook_banner" in kinds:
        ov.append({"type": "hook_banner", "text": short_phrase(first["text"], 7), "anchor": "begin", "dur": 3.0})
    if "title" in kinds:
        # Titular extractivo: la frase con más valor/gancho del fragmento, resumida
        best = max(order, key=lambda i: sents[i]["scores"]["value"] + sents[i]["scores"]["hook"])
        ov.append({"type": "title", "text": short_phrase(sents[best]["text"], 7), "anchor": "begin", "dur": 3.5})
    if "list" in kinds:
        items = [i for i in order if {"tip", "explanation", "number", "solution"} & set(sents[i]["labels"])
                 and sents[i]["scores"]["value"] >= 0.45][:4]
        for n, i in enumerate(items):
            ov.append({"type": "list_item", "text": short_phrase(sents[i]["text"], 6), "n": n + 1,
                       "anchor": "src", "src": sents[i]["start"] + 0.1, "dur": 3.2})
            sfx.append({"kind": "ding", "anchor": "src", "src": sents[i]["start"] + 0.1, "cause": "list"})
        if items:
            notes.append(f"Lista visual con {len(items)} ideas extraídas literalmente del discurso.")
    if "numbers" in kinds:
        nn = 0
        for i in plan["emphasis"]:
            t = words[i]["text"].strip(".,;:!?¿¡")
            if any(ch.isdigit() for ch in t):
                nxt = words[i + 1]["text"].strip(".,;:!?") if i + 1 < len(words) else ""
                label = f"{t} {nxt}" if nxt and len(nxt) <= 10 and not any(c.isdigit() for c in nxt) else t
                ov.append({"type": "number", "text": label.upper(), "anchor": "src", "src": words[i]["start"], "dur": 1.6})
                sfx.append({"kind": "hit", "anchor": "src", "src": words[i]["start"], "cause": "number"})
                nn += 1
        if nn:
            notes.append(f"{nn} cifras destacadas en pantalla.")
    if "stages" in kinds:
        seen = set()
        for i in order:
            for role in ("problem", "solution", "benefit", "cta"):
                if role in sents[i]["labels"] and role not in seen and i != order[0]:
                    seen.add(role)
                    ov.append({"type": "stage", "text": STAGE_LABELS[lk][role], "anchor": "src",
                               "src": sents[i]["start"], "dur": 2.2})
                    sfx.append({"kind": "whoosh", "anchor": "src", "src": sents[i]["start"], "cause": "stage"})
                    break
        missing = [r for r in ("problem", "solution", "benefit") if r not in seen]
        if missing:
            notes.append("El vídeo no contiene de forma explícita: " + ", ".join(missing) +
                         ". No se han añadido textos para suplirlo.")
    if "cta" in kinds:
        cta_s = next((i for i in order if "cta" in sents[i]["labels"]), None)
        brand_cta = (cfg.get("brand") or {}).get("cta", "").strip()
        if cta_s is not None:
            ov.append({"type": "cta", "text": short_phrase(sents[cta_s]["text"], 7), "anchor": "end", "dur": 2.8})
            notes.append("CTA final tomada literalmente del vídeo.")
        elif brand_cta:
            ov.append({"type": "cta", "text": brand_cta[:60], "anchor": "end", "dur": 2.8, "from_brand": True})
            notes.append("CTA final tomada de la configuración de marca (texto del usuario).")
        else:
            notes.append("Sin CTA: el vídeo no contiene una llamada a la acción y la marca no define una.")
    if "expressive" in kinds:
        n = 0
        for i in order:
            s = sents[i]
            f = s["features"]
            if not (f.get("emphatic") or f.get("humor") or f.get("surprise") or "!" in s["text"]):
                continue
            cand = [k for k in range(s["w0"], s["w1"]) if k in set(plan["emphasis"])] or \
                   [max(range(s["w0"], s["w1"]), key=lambda k: len(words[k]["text"]))]
            k = cand[0]
            ov.append({"type": "expressive", "text": words[k]["text"].strip(".,;:¿?").upper() +
                       ("!" if "!" in s["text"] else ""), "anchor": "src", "src": words[k]["start"], "dur": 1.2})
            n += 1
            if n >= 4:
                break
    if "progress" in kinds:
        ov.append({"type": "progress", "anchor": "begin", "dur": 9999})
    plan["overlays"] = ov
    plan["sfx"] = sfx
    return notes


def plan_sfx(plan: dict, style: dict) -> None:
    sc = style.get("sfx", {})
    if not sc.get("enabled"):
        plan["sfx"] = []
        return
    sfx = [s for s in plan.get("sfx", []) if s.get("cause") in sc.get("on", [])]
    if "zoom" in sc.get("on", []):
        for seg in plan["segments"]:
            for sh in seg["shots"]:
                if sh["zoom"] > 1.0 and sh.get("reason") == "énfasis":
                    sfx.append({"kind": sc["kind"], "anchor": "src", "src": sh["src_start"], "cause": "zoom"})
    if "broll" in sc.get("on", []):
        for seg in plan["segments"]:
            for sh in seg["shots"]:
                if sh.get("broll") or sh.get("card"):
                    sfx.append({"kind": sc["kind"], "anchor": "src", "src": sh["src_start"] - 0.15, "cause": "broll"})
    sfx.sort(key=lambda s: s["src"])
    plan["sfx"] = sfx[: sc.get("max", 4)]


# ---------------------------------------------------------------------------
# Plan completo
# ---------------------------------------------------------------------------

def target_duration(style: dict, cfg: dict, sents: list[dict]) -> float:
    d = cfg.get("duration", "auto")
    speech = speech_bounds(sents) * 1.08
    if d in (None, "auto", 0, "0"):
        return float(min(style["auto_duration"], max(8.0, speech)))
    return float(d)


def plan_version(style_key: str, analysis: dict, cfg: dict, media: dict, variant: int = 0,
                 used: list[dict] | None = None) -> dict:
    style = dict(STYLES[style_key])
    words = analysis["transcript"]["words"]
    sents = analysis["sentences"]
    lang = analysis.get("language", "es")
    used = used or []
    aspect = cfg.get("format", "9:16")
    W, H = FORMATS.get(aspect, FORMATS["9:16"])
    portrait = H > W
    brand = cfg.get("brand") or {}
    duration = media["duration"]
    notes, warnings = [], []

    subtitle_preset = style["subtitles"]
    music = style["music"]
    if variant:
        subtitle_preset = ALT_SUBTITLES[(ALT_SUBTITLES.index(subtitle_preset) + variant) % len(ALT_SUBTITLES)] \
            if subtitle_preset in ALT_SUBTITLES else subtitle_preset
        if music != "none":
            music = ALT_MUSIC[(ALT_MUSIC.index(music) + variant) % len(ALT_MUSIC)] if music in ALT_MUSIC else music
    if brand.get("subtitle_preset") and brand["subtitle_preset"] != "auto":
        subtitle_preset = brand["subtitle_preset"]
    if brand.get("music") and brand["music"] != "auto":
        music = brand["music"]

    plan: dict = {
        "schema": 1, "style": style_key, "style_name": style["name"], "variant": variant,
        "format": {"aspect": aspect, "width": W, "height": H, "fps": FPS},
        "source": {"width": media["width"], "height": media["height"], "duration": duration},
        "reframe": style.get("reframe", "face"),
        "segments": [], "transitions": [], "emphasis": [], "subtitle_overrides": {},
        "subtitles": {"enabled": True, "preset": subtitle_preset, "position": "auto",
                      "highlight": brand.get("highlight") or None, "font": brand.get("font") or None},
        "overlays": [], "sfx": [],
        "color": {"preset": style["color"]},
        "music": {"preset": music, "volume_db": style.get("music_db", -24), "duck": True},
        "logo": {"enabled": bool(brand.get("logo")), "path": brand.get("logo") or "", "position": "top-right",
                 "opacity": 0.9, "scale": 0.16},
        "letterbox": bool(style.get("letterbox")),
        "audio": {"loudnorm": -14.0},
        "selection": {}, "notes": notes, "warnings": warnings, "duration": 0.0,
    }

    if not sents:
        # Sin voz: montaje por escenas, sin subtítulos
        target = float(cfg.get("duration") if cfg.get("duration") not in (None, "auto") else min(30, duration))
        a = 0.0
        b = min(duration, target)
        plan["segments"] = [{"id": "s0", "src_start": q(a), "src_end": q(b), "role": "body", "sentence_ids": [],
                             "shots": []}]
        _split(plan["segments"][0], [sc["start"] for sc in analysis.get("scenes", [])])
        plan["subtitles"]["enabled"] = False
        warnings.append("No se detectó voz: versión sin subtítulos basada en escenas.")
        normalize_plan(plan, words, duration)
        plan["duration"] = build(plan, words)["duration"]
        return plan

    target = target_duration(style, cfg, sents)
    win, n_ = choose_window(style, sents, target, used, variant)
    notes += n_
    order = list(range(win["i"], win["j"] + 1))
    roles: dict[int, str] = {}
    hook = pick_hook(sents, order, target) if style.get("hook_reorder") else None
    if hook is not None and hook != order[0]:
        if hook in order:
            order.remove(hook)
        order.insert(0, hook)
        notes.append(f"Gancho adelantado desde {fmt_time(sents[hook]['start'])}: «{short_phrase(sents[hook]['text'], 10)}» "
                     f"(puntuación de gancho {sents[hook]['scores']['hook']:.2f}).")
        while len(order) > 2 and sum(window_duration(sents, i, i) for i in order) > target * 1.12:
            order.pop()
        # cerrar en una frase completa
        while len(order) > 2 and not sents[order[-1]]["features"]["ends_clean"]:
            order.pop()
    roles[order[0]] = "hook"
    if style.get("append_cta") and not any("cta" in sents[i]["labels"] for i in order):
        cta = next((s["id"] for s in sents if "cta" in s["labels"] and s["id"] > order[-1]
                    and s["scores"]["autonomy"] >= 0.4), None)
        if cta is not None:
            order.append(cta)
            roles[cta] = "cta"
            notes.append(f"CTA original añadida al final (desde {fmt_time(sents[cta]['start'])}).")
    for i in order[1:]:
        for r in ("problem", "solution", "benefit", "cta"):
            if r in sents[i]["labels"]:
                roles.setdefault(i, r)

    plan["selection"] = {"start": win["start"], "end": win["end"], "score": win["score"],
                         "sentence_ids": order, "target": target,
                         "first_hook": sents[order[0]]["scores"]["hook"]}
    first_s = sents[win["i"]]
    notes.insert(0, f"Fragmento {fmt_time(win['start'])}–{fmt_time(win['end'])} elegido (puntuación {win['score']:.2f}; "
                    f"gancho inicial {first_s['scores']['hook']:.2f}, claridad media, autonomía y cierre).")

    segs, stats = segments_from_sentences(order, sents, words, style, duration, roles)
    plan["segments"] = segs
    if stats["cuts"]:
        notes.append(f"{stats['cuts']} pausas > {style['max_gap']} s recortadas ({stats['saved_s']} s ahorrados).")
    if stats["fillers_removed"]:
        notes.append(f"{stats['fillers_removed']} muletillas eliminadas.")

    plan["emphasis"] = emphasis_words(words, order, sents, 0.0)
    notes += plan_shots(plan, style, sents, words, analysis, lang, portrait, cfg)
    notes += plan_overlays(plan, style, sents, words, order, lang, cfg)
    plan_sfx(plan, style)

    tr = style.get("transition", {})
    if tr.get("type", "cut") != "cut":
        plan["transitions"] = [{"after": s["id"], "type": tr["type"], "dur": tr["dur"]}
                               for s in segs[:-1]
                               if s["src_end"] - s["src_start"] > 1.2]
    warnings += normalize_plan(plan, words, duration)
    tl = build(plan, words)
    plan["duration"] = round(tl["duration"], 3)
    if plan["duration"] < target * 0.6:
        warnings.append(f"Duración resultante {plan['duration']:.0f} s, por debajo de la pedida ({target:.0f} s): "
                        "no hay más discurso aprovechable sin rellenar.")
    return plan


def plan_all(analysis: dict, cfg: dict, media: dict, styles: list[str] | None = None) -> tuple[dict[str, dict], list[str]]:
    """Crea los 10 planes evitando, si el material lo permite, repetir fragmento."""
    used: list[dict] = []
    plans, warnings = {}, []
    for key in styles or STYLE_ORDER:
        p = plan_version(key, analysis, cfg, media, 0, used)
        sel = p.get("selection") or {}
        if sel:
            used.append({"start": sel["start"], "end": sel["end"]})
        plans[key] = p
    sels = [(p["selection"]["start"], p["selection"]["end"]) for p in plans.values() if p.get("selection")]
    distinct = []
    for a, b in sels:
        if all(overlap({"start": a, "end": b}, {"start": c, "end": d}) < 0.5 for c, d in distinct):
            distinct.append((a, b))
    if sels and len(distinct) < len(sels):
        warnings.append(f"El material solo permite {len(distinct)} fragmento(s) distinto(s) para la duración "
                        f"pedida: varias versiones son tratamientos alternativos del mismo fragmento.")
    return plans, warnings
