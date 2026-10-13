"""Subtítulos y rótulos en ASS (renderizados por libass dentro de FFmpeg) y exportación SRT.

Zonas seguras (9:16): se evita el 12 % superior y el 22 % inferior (interfaz de
TikTok / Reels / Shorts) y el margen derecho de los botones. La posición se ajusta
por plano para no tapar la cara.
"""
from __future__ import annotations

import re

from .geometry import face_box_out
from .timeline import resolve_anchor

FONT_FAMILIES = ["Poppins", "Poppins Medium", "Poppins SemiBold", "Poppins ExtraBold", "Poppins Black", "Anton",
                 "Bebas Neue", "Archivo Black", "Bangers", "Luckiest Guy", "Permanent Marker", "DM Serif Display",
                 "Lato"]

# size: px para una salida de 1920 px de alto en 9:16 (se escala con el lado corto)
PRESETS: dict[str, dict] = {
    "bold_pop": {"name": "Bold Pop", "font": "Poppins Black", "size": 84, "upper": True, "mode": "pop",
                 "primary": "#FFFFFF", "outline": "#000000", "ow": 7, "shadow": 3, "hl": "#FFD84D",
                 "words": 3, "chars": 18, "strip": True, "pos": "bottom"},
    "impact_caps": {"name": "Impacto empresarial", "font": "Anton", "size": 96, "upper": True, "mode": "pop",
                    "primary": "#FFFFFF", "outline": "#0A0A0A", "ow": 6, "shadow": 0, "hl": "#2EE59D",
                    "words": 2, "chars": 16, "strip": True, "pos": "bottom", "scale": 108},
    "cinema_serif": {"name": "Cine serif", "font": "DM Serif Display", "size": 64, "upper": False, "mode": "fade",
                     "primary": "#F4EFE6", "outline": "#000000", "ow": 0, "shadow": 2, "blur": 4, "hl": "#E8C766",
                     "words": 7, "chars": 30, "strip": False, "pos": "lower"},
    "story_soft": {"name": "Historia suave", "font": "Poppins Medium", "size": 60, "upper": False, "mode": "fade",
                   "primary": "#FFFFFF", "outline": "#000000", "ow": 3, "shadow": 2, "blur": 1, "hl": "#FFC37A",
                   "words": 6, "chars": 28, "strip": False, "pos": "bottom"},
    "edu_box": {"name": "Educativo con caja", "font": "Poppins SemiBold", "size": 62, "upper": False, "mode": "box",
                "primary": "#FFFFFF", "outline": "#000000", "ow": 0, "shadow": 0, "back": "#0B1F17", "back_a": 0.18,
                "hl": "#E8C766", "words": 5, "chars": 26, "strip": False, "pos": "bottom"},
    "word_single": {"name": "Palabra a palabra", "font": "Anton", "size": 128, "upper": True, "mode": "single",
                    "primary": "#FFFFFF", "outline": "#000000", "ow": 8, "shadow": 4, "hl": "#FFD84D",
                    "words": 1, "chars": 14, "strip": True, "pos": "bottom"},
    "sales_punch": {"name": "Ventas", "font": "Poppins ExtraBold", "size": 80, "upper": True, "mode": "pop",
                    "primary": "#FFFFFF", "outline": "#06140E", "ow": 6, "shadow": 2, "hl": "#2EE59D",
                    "words": 3, "chars": 18, "strip": True, "pos": "bottom"},
    "minimal_lower": {"name": "Minimal", "font": "Lato", "size": 50, "upper": False, "mode": "fade",
                      "primary": "#FFFFFF", "outline": "#000000", "ow": 0, "shadow": 1, "blur": 2, "hl": "#FFFFFF",
                      "words": 7, "chars": 32, "strip": False, "pos": "lower", "no_emph": True},
    "meme_bounce": {"name": "Meme rebote", "font": "Luckiest Guy", "size": 92, "upper": True, "mode": "bounce",
                    "primary": "#FFFFFF", "outline": "#000000", "ow": 8, "shadow": 4, "hl": "#FFE600",
                    "words": 2, "chars": 14, "strip": True, "pos": "bottom",
                    "palette": ["#FFE600", "#2EE59D", "#FF5CA8", "#4DD2FF"]},
    "karaoke_fill": {"name": "Karaoke", "font": "Poppins ExtraBold", "size": 80, "upper": True, "mode": "karaoke",
                     "primary": "#FFD84D", "secondary": "#FFFFFF", "outline": "#000000", "ow": 6, "shadow": 2,
                     "hl": "#FFD84D", "words": 4, "chars": 20, "strip": True, "pos": "bottom"},
    "neon_glow": {"name": "Neón", "font": "Poppins Bold", "size": 80, "upper": True, "mode": "pop",
                  "primary": "#FFFFFF", "outline": "#2EE59D", "ow": 3, "shadow": 0, "blur": 6, "hl": "#2EE59D",
                  "words": 3, "chars": 18, "strip": True, "pos": "bottom"},
    "marker": {"name": "Rotulador", "font": "Permanent Marker", "size": 78, "upper": False, "mode": "pop",
               "primary": "#FFFFFF", "outline": "#000000", "ow": 5, "shadow": 2, "hl": "#FF8A3D",
               "words": 3, "chars": 18, "strip": True, "pos": "bottom"},
    "classic_white": {"name": "Clásico accesible", "font": "Poppins SemiBold", "size": 64, "upper": False,
                      "mode": "fade", "primary": "#FFFFFF", "outline": "#000000", "ow": 4, "shadow": 1,
                      "hl": "#FFD84D", "words": 6, "chars": 28, "strip": False, "pos": "bottom"},
}

BRAND_GREEN = "#0F3D2E"
BRAND_GOLD = "#D4AF37"


def ass_color(hex_color: str, alpha: float = 0.0) -> str:
    h = (hex_color or "#FFFFFF").lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = int(max(0, min(1, alpha)) * 255)
    return f"&H{a:02X}{b}{g}{r}".upper()


def esc(text: str) -> str:
    """Escapa texto para ASS: sin llaves (etiquetas) ni barras invertidas."""
    t = str(text).replace("\\", "/").replace("{", "(").replace("}", ")")
    return re.sub(r"[\r\n]+", " ", t)


def ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def safe_font(name: str | None, default: str) -> tuple[str, bool]:
    """Devuelve (familia, negrita) solo de la lista blanca de fuentes instaladas."""
    if not name:
        name = default
    if name == "Poppins Bold":
        return "Poppins", True
    if name in FONT_FAMILIES:
        return name, False
    return (default, False) if default != "Poppins Bold" else ("Poppins", True)


def display_word(w: str, p: dict) -> str:
    if p.get("strip"):
        w = re.sub(r"[.,;:…]+$", "", w)
        w = w.lstrip("¿¡")
    return w.upper() if p.get("upper") else w


def group_cues(words: list[dict], p: dict) -> list[list[dict]]:
    cues: list[list[dict]] = []
    cur: list[dict] = []
    for i, w in enumerate(words):
        if cur:
            prev = cur[-1]
            chars = sum(len(x["text"]) + 1 for x in cur) + len(w["text"])
            if (len(cur) >= p["words"] or chars > p["chars"] * (2 if p["mode"] in ("fade", "box") else 1)
                    or w["start"] - prev["end"] > 0.6 or prev["text"].endswith((".", "?", "!", "…"))
                    or w["seg"] != prev["seg"] and w["start"] - prev["end"] > 0.15):
                cues.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    return cues


def _break_lines(parts: list[str], max_chars: int) -> list[str]:
    """Inserta un salto de línea (\\N) cerca del centro si el texto es largo."""
    total = sum(len(re.sub(r"\{[^}]*\}", "", x)) + 1 for x in parts)
    if total <= max_chars or len(parts) < 2:
        return parts
    acc, best, best_d = 0, 1, 1e9
    for k, x in enumerate(parts[:-1]):
        acc += len(re.sub(r"\{[^}]*\}", "", x)) + 1
        d = abs(acc - total / 2)
        if d < best_d:
            best, best_d = k + 1, d
    return parts[:best - 1] + [parts[best - 1] + "\\N"] + parts[best:]


class AssBuilder:
    def __init__(self, plan: dict, tl: dict, brand: dict | None = None):
        self.plan, self.tl = plan, tl
        self.W, self.H = plan["format"]["width"], plan["format"]["height"]
        self.k = min(self.W, self.H) / 1080
        self.vertical = self.H > self.W
        self.brand = brand or {}
        self.events: list[str] = []
        self.styles: list[str] = []
        self.src_w, self.src_h = plan["source"]["width"], plan["source"]["height"]

    # -- posiciones --------------------------------------------------------
    def band_y(self, name: str) -> float:
        if self.vertical:
            return {"bottom": 0.70, "lower": 0.755, "middle": 0.55, "top": 0.22, "mid_low": 0.58}[name]
        if self.W > self.H:
            return {"bottom": 0.855, "lower": 0.88, "middle": 0.5, "top": 0.14, "mid_low": 0.66}[name]
        return {"bottom": 0.8, "lower": 0.84, "middle": 0.55, "top": 0.16, "mid_low": 0.64}[name]

    def face_at(self, t: float) -> tuple[float, float] | None:
        for sh in self.tl["shots"]:
            if sh["out_start"] <= t < sh["out_end"]:
                return face_box_out(sh, self.src_w, self.src_h, self.W, self.H, self.plan.get("reframe", "face"))
        return None

    def choose_y(self, start: float, end: float, preferred: str, text_h: float, alts: list[str]) -> float:
        """Primera franja (preferida o alternativas) que no se solapa con la cara."""
        faces = [f for f in (self.face_at(start + (end - start) * r) for r in (0.1, 0.5, 0.9)) if f]
        for name in [preferred, *alts]:
            y = self.band_y(name)
            top, bot = y - text_h / 2 / self.H, y + text_h / 2 / self.H
            if not any(not (bot < f0 or top > f1) for f0, f1 in faces):
                return y * self.H
        return self.band_y(preferred) * self.H

    # -- estilos -------------------------------------------------------------
    def add_style(self, name: str, font: str, size: float, primary: str, secondary: str, outline: str,
                  back: str, bold: bool, ow: float, shadow: float, border_style: int = 1, align: int = 5,
                  spacing: float = 0.0) -> None:
        mv = 0
        ml, mr = (90, 170) if self.vertical else (120, 120)
        self.styles.append(
            f"Style: {name},{font},{size:.0f},{primary},{secondary},{outline},{back},{-1 if bold else 0},0,0,0,"
            f"100,100,{spacing:.1f},0,{border_style},{ow:.1f},{shadow:.1f},{align},{ml},{mr},{mv},1")

    def ev(self, start: float, end: float, style: str, text: str, layer: int = 0) -> None:
        if end - start < 0.03:
            return
        self.events.append(f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}")

    # -- subtítulos ------------------------------------------------------------
    def subtitles(self) -> None:
        sub = self.plan.get("subtitles") or {}
        if not sub.get("enabled", True):
            return
        p = dict(PRESETS.get(sub.get("preset") or "bold_pop", PRESETS["bold_pop"]))
        font, bold = safe_font(sub.get("font"), p["font"])
        size = p["size"] * self.k * float(sub.get("scale", 1.0))
        hl = sub.get("highlight") or p["hl"]
        border = 3 if p["mode"] == "box" else 1
        back = ass_color(p.get("back", "#000000"), p.get("back_a", 0.4)) if border == 3 else ass_color("#000000", 0.45)
        primary = ass_color(p["primary"])
        secondary = ass_color(p.get("secondary", p["primary"]))
        self.add_style("Sub", font, size, primary, secondary, ass_color(p["outline"]), back, bold,
                       p["ow"] * self.k, p["shadow"] * self.k, border)
        words = [dict(w, text=display_word(w["text"], p)) for w in self.tl["words"]]
        words = [w for w in words if w["text"]]
        if not words:
            return
        cues = group_cues(words, p)
        pos = sub.get("position", "auto")
        hl_tag = "{\\c" + ass_color(hl) + "}"
        reset = "{\\c" + primary + "\\fscx100\\fscy100\\frz0}"
        blur = f"\\blur{p['blur']}" if p.get("blur") else ""
        x = self.W * (0.47 if self.vertical else 0.5)
        lines_h = size * (2.4 if p["mode"] in ("fade", "box") else 1.3)
        for ci, cue in enumerate(cues):
            c_start = cue[0]["start"]
            nxt = cues[ci + 1][0]["start"] if ci + 1 < len(cues) else self.tl["duration"]
            c_end = min(cue[-1]["end"] + 0.3, nxt)
            if pos == "auto":
                y = self.choose_y(c_start, c_end, p["pos"], lines_h, ["top", "mid_low"])
            else:
                y = self.band_y(pos) * self.H
            base = f"{{\\an5\\pos({x:.0f},{y:.0f}){blur}}}"
            emph = (lambda w: w["emph"] and not p.get("no_emph"))
            if p["mode"] == "karaoke":
                parts = []
                for k, w in enumerate(cue):
                    nd = (cue[k + 1]["start"] if k + 1 < len(cue) else c_end) - w["start"]
                    parts.append(f"{{\\kf{max(1, int(round(nd * 100)))}}}" + esc(w["text"]))
                self.ev(c_start, c_end, "Sub", base + " ".join(_break_lines(parts, p["chars"])))
            elif p["mode"] == "fade":
                parts = [(hl_tag + esc(w["text"]) + reset) if emph(w) else esc(w["text"]) for w in cue]
                self.ev(c_start, c_end, "Sub", base + "{\\fad(140,120)}" + " ".join(_break_lines(parts, p["chars"])))
            elif p["mode"] == "single":
                for k, w in enumerate(cue):
                    end = cue[k + 1]["start"] if k + 1 < len(cue) else c_end
                    col = hl_tag if emph(w) else ""
                    self.ev(w["start"], max(end, w["start"] + 0.12), "Sub",
                            base + "{\\fscx78\\fscy78\\t(0,80,\\fscx100\\fscy100)}" + col + esc(w["text"]))
            else:  # pop | box | bounce: un evento por palabra activa
                sc = p.get("scale", 112)
                for k, w in enumerate(cue):
                    start = c_start if k == 0 else w["start"]
                    end = cue[k + 1]["start"] if k + 1 < len(cue) else c_end
                    parts = []
                    for m, o in enumerate(cue):
                        t = esc(o["text"])
                        if m == k:
                            if p["mode"] == "bounce":
                                pal = p["palette"]
                                col = ass_color(pal[(ci + m) % len(pal)])
                                rot = (-4, 3, -2, 4)[(ci + m) % 4]
                                parts.append(f"{{\\c{col}\\frz{rot}\\fscx{sc + 10}\\fscy{sc + 10}}}{t}{reset}")
                            elif p["mode"] == "box":
                                parts.append(f"{hl_tag}{t}{reset}")
                            else:
                                parts.append(f"{hl_tag}{{\\fscx{sc}\\fscy{sc}}}{t}{reset}")
                        elif emph(o):
                            parts.append(f"{hl_tag}{t}{reset}")
                        else:
                            parts.append(t)
                    intro = "{\\fscx82\\fscy82\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
                    # tras \r se pierde la posición: se repite el bloque base al principio
                    self.ev(start, end, "Sub", base + intro + " ".join(_break_lines(parts, p["chars"])))

    # -- rótulos ---------------------------------------------------------------
    def overlays(self) -> None:
        primary = self.brand.get("primary") or BRAND_GREEN
        accent = self.brand.get("accent") or BRAND_GOLD
        k = self.k
        self.add_style("Title", "Poppins ExtraBold", 66 * k, ass_color("#FFFFFF"), ass_color("#FFFFFF"),
                       ass_color(primary, 0.05), ass_color(primary, 0.08), False, 18 * k, 0, 3)
        self.add_style("Banner", "Poppins Black", 62 * k, ass_color("#0A0A0A"), ass_color("#0A0A0A"),
                       ass_color(accent), ass_color(accent), False, 16 * k, 0, 3)
        self.add_style("Item", "Poppins SemiBold", 54 * k, ass_color("#FFFFFF"), ass_color("#FFFFFF"),
                       ass_color("#0B0F0D", 0.15), ass_color("#0B0F0D", 0.15), False, 14 * k, 0, 3, align=4)
        self.add_style("Big", "Anton", 150 * k, ass_color(accent), ass_color(accent), ass_color("#000000"),
                       ass_color("#000000", 0.5), False, 8 * k, 4 * k, 1)
        self.add_style("Stage", "Poppins ExtraBold", 44 * k, ass_color("#FFFFFF"), ass_color("#FFFFFF"),
                       ass_color(primary), ass_color(primary), False, 12 * k, 0, 3, align=7)
        self.add_style("Expr", "Bangers", 130 * k, ass_color("#FFE600"), ass_color("#FFE600"), ass_color("#000000"),
                       ass_color("#000000", 0.4), False, 9 * k, 5 * k, 1)
        self.add_style("Card", "Anton", 140 * k, ass_color(accent), ass_color(accent), ass_color("#000000"),
                       ass_color("#000000", 0.6), False, 4 * k, 0, 1)
        self.add_style("Bar", "Poppins", 20, ass_color(accent), ass_color(accent), ass_color(accent),
                       ass_color(accent), False, 0, 0, 1, align=7)
        cx = self.W * (0.47 if self.vertical else 0.5)
        list_n = 0
        for ov in self.plan.get("overlays", []):
            if ov.get("enabled") is False:
                continue
            if ov["type"] == "progress":
                d = self.tl["duration"]
                h = max(8, int(10 * k))
                self.ev(0, d, "Bar", f"{{\\an7\\pos(0,0)\\clip(0,0,0,{h})\\t(0,{int(d * 1000)},\\clip(0,0,{self.W},{h}))\\p1}}"
                                     f"m 0 0 l {self.W} 0 {self.W} {h} 0 {h}{{\\p0}}", layer=5)
                continue
            span = resolve_anchor(self.tl, ov)
            if not span:
                continue
            a, b = span
            text = esc(ov.get("text", ""))
            if not text:
                continue
            t = ov["type"]
            if t in ("title", "hook_banner"):
                y = self.choose_y(a, b, "top", 90 * k, ["mid_low"])
                st = "Title" if t == "title" else "Banner"
                self.ev(a, b, st, f"{{\\an5\\pos({cx:.0f},{y:.0f})\\fad(180,180)\\fscx92\\fscy92\\t(0,160,\\fscx100\\fscy100)}}"
                                  f"{text}", layer=3)
            elif t == "list_item":
                list_n += 1
                y = self.choose_y(a, b, "top", 80 * k, ["mid_low"])
                x0 = int(self.W * 0.08)
                self.ev(a, b, "Item", f"{{\\an4\\move({x0 - 40},{y:.0f},{x0},{y:.0f},0,160)\\fad(120,160)}}"
                                      f"{{\\c{ass_color(accent)}}}{ov.get('n', list_n)}. {{\\c&HFFFFFF&}}{text}", layer=3)
            elif t == "number":
                y = self.choose_y(a, b, "top", 160 * k, ["mid_low", "middle"])
                self.ev(a, b, "Big", f"{{\\an5\\pos({cx:.0f},{y:.0f})\\fscx60\\fscy60\\t(0,120,\\fscx105\\fscy105)"
                                     f"\\t(120,200,\\fscx100\\fscy100)\\fad(60,180)}}{text}", layer=4)
            elif t == "stage":
                self.ev(a, b, "Stage", f"{{\\an7\\pos({int(self.W * 0.07)},{int(self.H * (0.135 if self.vertical else 0.08))})"
                                       f"\\fad(120,200)}}{text}", layer=4)
            elif t == "cta":
                y = self.choose_y(a, b, "mid_low", 100 * k, ["top"])
                self.ev(a, b, "Banner", f"{{\\an5\\pos({cx:.0f},{y:.0f})\\fad(200,0)\\fscx85\\fscy85"
                                        f"\\t(0,200,\\fscx100\\fscy100)}}{text}", layer=4)
            elif t == "expressive":
                y = self.choose_y(a, b, "top", 140 * k, ["mid_low"])
                self.ev(a, b, "Expr", f"{{\\an5\\pos({cx:.0f},{y:.0f})\\frz-7\\fscx40\\fscy40"
                                      f"\\t(0,110,\\fscx115\\fscy115)\\t(110,200,\\fscx100\\fscy100)\\fad(0,150)}}{text}",
                        layer=4)
        # Rótulos de los planos "tarjeta" (alternativa interna al B-roll)
        for sh in self.tl["shots"]:
            if sh.get("card") and sh["card"].get("text"):
                self.ev(sh["out_start"], sh["out_end"], "Card",
                        f"{{\\an5\\pos({self.W / 2:.0f},{self.H * 0.42:.0f})\\fscx80\\fscy80"
                        f"\\t(0,250,\\fscx100\\fscy100)\\fad(150,150)}}{esc(sh['card']['text'])}", layer=2)

    def build(self) -> str:
        self.subtitles()
        self.overlays()
        head = (
            "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
            f"PlayResX: {self.W}\nPlayResY: {self.H}\nYCbCr Matrix: TV.709\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        body = "\n".join(self.styles)
        evs = "\n".join(self.events)
        return (head + body + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
                "Effect, Text\n" + evs + "\n")


def build_ass(plan: dict, tl: dict, brand: dict | None = None) -> str:
    return AssBuilder(plan, tl, brand).build()


def srt_from_words(words: list[dict], max_words: int = 7, max_chars: int = 42) -> str:
    def stamp(t: float) -> str:
        ms = int(round(max(0.0, t) * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    p = {"words": max_words, "chars": max_chars, "mode": "srt"}
    cues = group_cues(words, p)
    out = []
    for n, cue in enumerate(cues, 1):
        end = cue[-1]["end"]
        if n < len(cues):
            end = min(end + 0.2, cues[n][0]["start"])
        text = " ".join(w["text"] for w in cue)
        out.append(f"{n}\n{stamp(cue[0]['start'])} --> {stamp(end)}\n{text}\n")
    return "\n".join(out)
