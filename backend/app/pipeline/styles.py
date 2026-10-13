"""Las 10 plantillas editoriales. Cada una cambia decisiones de montaje, no solo el aspecto.

- weights: cómo se elige el fragmento (ver semantic.candidate_windows).
- max_gap: pausa máxima que se conserva entre palabras (el resto se corta).
- hook_reorder: si existe una frase-gancho fuerte fuera del fragmento, se abre con ella.
- zoom: "none" | "punch" (saltos en palabras clave) | "alternate" (cambio de encuadre por frase) |
        "push" (acercamiento lento) | "comic" (zoom rápido exagerado pero acotado) | "speaker" (podcast)
"""
from __future__ import annotations

STYLES: dict[str, dict] = {
    "viral": {
        "index": 1, "name": "Viral dinámico",
        "summary": "Subtítulos grandes animados, cortes dinámicos y zooms en momentos clave.",
        "weights": {"hook": 0.45, "clarity": 0.15, "value": 0.15, "retention": 0.25, "energy": 0.1,
                    "labels": {"surprise": 0.06, "question": 0.06}},
        "auto_duration": 30, "max_gap": 0.25, "pad": 0.08, "remove_fillers": True, "hook_reorder": True,
        "zoom": {"mode": "punch", "scale": 1.18, "min_spacing": 3.5},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "bold_pop", "color": "vibrant", "music": "upbeat_pulse", "music_db": -24,
        "sfx": {"enabled": True, "on": ["zoom"], "kind": "whoosh", "max": 4},
        "broll": {"enabled": True, "max_ratio": 0.18, "min_gap": 6.0, "fallback": "none"},
        "overlays": ["hook_banner"], "reframe": "face",
    },
    "empresarial": {
        "index": 2, "name": "Empresarial intenso",
        "summary": "Frases cortas, cambios de encuadre, énfasis en cifras y cero pausas muertas.",
        "weights": {"hook": 0.35, "clarity": 0.2, "value": 0.3, "retention": 0.15,
                    "labels": {"number": 0.08, "tip": 0.05, "benefit": 0.04}},
        "auto_duration": 30, "max_gap": 0.15, "pad": 0.06, "remove_fillers": True, "hook_reorder": True,
        "zoom": {"mode": "alternate", "scale": 1.14},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "impact_caps", "color": "punchy", "music": "corporate_drive", "music_db": -25,
        "sfx": {"enabled": True, "on": ["number"], "kind": "hit", "max": 3},
        "broll": {"enabled": True, "max_ratio": 0.2, "min_gap": 5.0, "fallback": "card"},
        "overlays": ["numbers"], "reframe": "face",
    },
    "cine": {
        "index": 3, "name": "Cinematográfico",
        "summary": "Etalonaje, música ambiental, fundidos suaves, B-roll y tipografía elegante.",
        "weights": {"hook": 0.2, "clarity": 0.3, "value": 0.15, "narrative": 0.2, "retention": 0.15},
        "auto_duration": 45, "max_gap": 0.7, "pad": 0.25, "remove_fillers": True, "hook_reorder": False,
        "zoom": {"mode": "push", "scale": 1.06},
        "transition": {"type": "fade", "dur": 0.35},
        "subtitles": "cinema_serif", "color": "teal_orange", "music": "ambient_pad", "music_db": -21,
        "sfx": {"enabled": False},
        "broll": {"enabled": True, "max_ratio": 0.3, "min_gap": 4.0, "fallback": "none"},
        "overlays": [], "reframe": "face", "letterbox": True,
    },
    "storytelling": {
        "index": 4, "name": "Storytelling",
        "summary": "El fragmento con más interés narrativo, en orden: inicio, desarrollo y cierre.",
        "weights": {"hook": 0.2, "clarity": 0.2, "value": 0.05, "narrative": 0.45, "retention": 0.1,
                    "labels": {"anecdote": 0.12, "closure": 0.06}},
        "auto_duration": 60, "max_gap": 0.9, "pad": 0.3, "remove_fillers": True, "hook_reorder": False,
        "zoom": {"mode": "push", "scale": 1.05},
        "transition": {"type": "fade", "dur": 0.4},
        "subtitles": "story_soft", "color": "warm_film", "music": "emotional_keys", "music_db": -22,
        "sfx": {"enabled": False},
        "broll": {"enabled": True, "max_ratio": 0.2, "min_gap": 6.0, "fallback": "none"},
        "overlays": ["title"], "reframe": "face",
    },
    "educativo": {
        "index": 5, "name": "Educativo",
        "summary": "Titular, lista visual de ideas, conceptos resaltados y subtítulos muy legibles.",
        "weights": {"hook": 0.15, "clarity": 0.3, "value": 0.45, "retention": 0.1,
                    "labels": {"tip": 0.08, "explanation": 0.08, "number": 0.04}},
        "auto_duration": 45, "max_gap": 0.35, "pad": 0.12, "remove_fillers": True, "hook_reorder": False,
        "zoom": {"mode": "none"},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "edu_box", "color": "clean_bright", "music": "lofi_soft", "music_db": -27,
        "sfx": {"enabled": True, "on": ["list"], "kind": "ding", "max": 4},
        "broll": {"enabled": True, "max_ratio": 0.2, "min_gap": 6.0, "fallback": "card"},
        "overlays": ["title", "list", "numbers"], "reframe": "face",
    },
    "podcast": {
        "index": 6, "name": "Podcast viral",
        "summary": "Plano centrado en quien habla, reencuadres, cortes en pausas y subtítulo palabra a palabra.",
        "weights": {"hook": 0.35, "clarity": 0.2, "value": 0.15, "retention": 0.3, "energy": 0.1},
        "auto_duration": 40, "max_gap": 0.3, "pad": 0.1, "remove_fillers": False, "hook_reorder": True,
        "zoom": {"mode": "speaker", "scale": 1.22},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "word_single", "color": "neutral_contrast", "music": "none", "music_db": -30,
        "sfx": {"enabled": False},
        "broll": {"enabled": False},
        "overlays": [], "reframe": "face_tight",
    },
    "ventas": {
        "index": 7, "name": "Ventas y conversión",
        "summary": "Gancho, problema, solución, beneficio y CTA solo si aparece en el vídeo o en la marca.",
        "weights": {"hook": 0.3, "clarity": 0.2, "value": 0.2, "retention": 0.15,
                    "labels": {"problem": 0.1, "solution": 0.1, "benefit": 0.08, "cta": 0.1}},
        "auto_duration": 35, "max_gap": 0.2, "pad": 0.08, "remove_fillers": True, "hook_reorder": True,
        "zoom": {"mode": "punch", "scale": 1.12, "min_spacing": 5.0},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "sales_punch", "color": "vibrant", "music": "corporate_drive", "music_db": -25,
        "sfx": {"enabled": True, "on": ["stage"], "kind": "whoosh", "max": 3},
        "broll": {"enabled": True, "max_ratio": 0.18, "min_gap": 6.0, "fallback": "none"},
        "overlays": ["stages", "cta"], "reframe": "face", "append_cta": True,
    },
    "minimal": {
        "index": 8, "name": "Minimalista premium",
        "summary": "Edición limpia, subtítulos discretos, colores sobrios y cortes naturales.",
        "weights": {"hook": 0.2, "clarity": 0.4, "value": 0.25, "retention": 0.15},
        "auto_duration": 30, "max_gap": 0.6, "pad": 0.2, "remove_fillers": True, "hook_reorder": False,
        "zoom": {"mode": "none"},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "minimal_lower", "color": "muted_premium", "music": "none", "music_db": -30,
        "sfx": {"enabled": False},
        "broll": {"enabled": False},
        "overlays": [], "reframe": "face",
    },
    "memes": {
        "index": 9, "name": "Memes y humor",
        "summary": "Zooms cómicos, efectos de sonido, textos expresivos y cambios de ritmo con sentido.",
        "weights": {"hook": 0.35, "clarity": 0.1, "value": 0.05, "retention": 0.2, "energy": 0.3,
                    "labels": {"humor": 0.12, "emphatic": 0.08, "surprise": 0.06}},
        "auto_duration": 25, "max_gap": 0.25, "pad": 0.08, "remove_fillers": False, "hook_reorder": True,
        "zoom": {"mode": "comic", "scale": 1.35, "min_spacing": 3.0},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "meme_bounce", "color": "comic_pop", "music": "playful", "music_db": -24,
        "sfx": {"enabled": True, "on": ["zoom"], "kind": "boing", "max": 5},
        "broll": {"enabled": False},
        "overlays": ["expressive"], "reframe": "face",
    },
    "retencion": {
        "index": 10, "name": "Retención optimizada",
        "summary": "Gancho fuerte, alternancia visual razonable, barra de progreso e imágenes de apoyo.",
        "weights": {"hook": 0.5, "clarity": 0.15, "value": 0.15, "retention": 0.2,
                    "labels": {"question": 0.06, "surprise": 0.06}},
        "auto_duration": 30, "max_gap": 0.2, "pad": 0.08, "remove_fillers": True, "hook_reorder": True,
        "zoom": {"mode": "alternate", "scale": 1.1},
        "transition": {"type": "cut", "dur": 0.0},
        "subtitles": "karaoke_fill", "color": "vibrant", "music": "upbeat_pulse", "music_db": -26,
        "sfx": {"enabled": True, "on": ["broll"], "kind": "whoosh", "max": 4},
        "broll": {"enabled": True, "max_ratio": 0.25, "min_gap": 5.0, "fallback": "card"},
        "overlays": ["hook_banner", "progress"], "reframe": "face",
    },
}

STYLE_ORDER = sorted(STYLES, key=lambda k: STYLES[k]["index"])

# Variantes alternativas usadas al pedir "Regenerar" (rotan subtítulos y música).
ALT_SUBTITLES = ["bold_pop", "karaoke_fill", "impact_caps", "neon_glow", "sales_punch", "classic_white"]
ALT_MUSIC = ["upbeat_pulse", "corporate_drive", "lofi_soft", "ambient_pad", "emotional_keys", "playful"]

COLOR_GRADES = {
    "none": "",
    "vibrant": "eq=contrast=1.06:saturation=1.22:brightness=0.01",
    "punchy": "eq=contrast=1.14:saturation=1.12,unsharp=5:5:0.6",
    "teal_orange": ("colorbalance=rs=-0.06:gs=0.0:bs=0.08:rh=0.08:gh=0.02:bh=-0.06,"
                    "eq=contrast=1.08:saturation=1.05,curves=preset=medium_contrast,vignette=angle=PI/5"),
    "warm_film": ("colorbalance=rs=0.04:bs=-0.03:rm=0.05:bm=-0.04,eq=contrast=1.04:saturation=0.95:gamma=1.02,"
                  "curves=all='0/0.04 0.5/0.52 1/0.96',vignette=angle=PI/5"),
    "clean_bright": "eq=brightness=0.025:contrast=1.04:saturation=1.06",
    "neutral_contrast": "eq=contrast=1.08:saturation=1.02",
    "muted_premium": "eq=contrast=1.05:saturation=0.82:gamma=0.98",
    "comic_pop": "eq=contrast=1.1:saturation=1.38",
    "cool_modern": "colorbalance=bs=0.05:bm=0.03:rh=-0.02,eq=contrast=1.06:saturation=1.0",
    "black_white": "hue=s=0,eq=contrast=1.15",
}

MUSIC_PRESETS = ["none", "upbeat_pulse", "corporate_drive", "ambient_pad", "emotional_keys", "lofi_soft",
                 "playful"]

FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}

DURATIONS = [15, 30, 45, 60, 90]


def public_styles() -> list[dict]:
    return [{"key": k, "index": STYLES[k]["index"], "name": STYLES[k]["name"], "summary": STYLES[k]["summary"],
             "subtitles": STYLES[k]["subtitles"], "color": STYLES[k]["color"], "music": STYLES[k]["music"]}
            for k in STYLE_ORDER]
