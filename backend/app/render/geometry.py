"""Geometría de reencuadre: qué rectángulo de la fuente se ve en cada plano."""
from __future__ import annotations

FACE_Y = 0.38  # posición vertical deseada de la cara dentro del encuadre (desde arriba)


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def crop_box(shot: dict, sw: int, sh: int, ow: int, oh: int, reframe: str = "face", cx: float | None = None) -> dict:
    """Rectángulo de recorte (en píxeles de la fuente) para un plano.

    mode = "crop": recorte directo; "fit": la fuente cabe entera sobre fondo desenfocado
    (p. ej. vídeo vertical exportado a 16:9).
    """
    ar, sar = ow / oh, sw / sh
    if sar < ar * 0.8:
        return {"mode": "fit", "x": 0, "y": 0, "w": sw, "h": sh}
    if sar >= ar:
        bw, bh = sh * ar, sh
    else:
        bw, bh = sw, sw / ar
    z = float(shot.get("zoom") or 1.0)
    if reframe == "face_tight" and shot.get("face_h"):
        z *= 1.12
    z = max(1.0, min(z, 2.0))
    w, h = bw / z, bh / z
    fx = (shot.get("cx", 0.5) if cx is None else cx) * sw
    fy = shot.get("cy", 0.42) * sh
    x = fx - w / 2
    y = fy - FACE_Y * h if shot.get("face_h") else (sh - h) / 2
    x = min(max(0.0, x), sw - w)
    y = min(max(0.0, y), sh - h)
    return {"mode": "crop", "x": int(x) // 2 * 2, "y": int(y) // 2 * 2, "w": _even(min(w, sw)), "h": _even(min(h, sh))}


def face_box_out(shot: dict, sw: int, sh: int, ow: int, oh: int, reframe: str = "face") -> tuple[float, float] | None:
    """Franja vertical (0-1 de la salida) ocupada por la cara en un plano, o None."""
    if not shot.get("face_h") or shot.get("broll") or shot.get("card"):
        return None
    b = crop_box(shot, sw, sh, ow, oh, reframe)
    fh = shot["face_h"] * sh
    cy = shot["cy"] * sh
    if b["mode"] == "fit":
        scale = min(ow / sw, oh / sh)
        top = (oh - sh * scale) / 2
        return ((cy - fh * 0.6) * scale + top) / oh, ((cy + fh * 0.75) * scale + top) / oh
    # la caja de la cara se amplía (pelo arriba, barbilla abajo)
    return (cy - fh * 0.6 - b["y"]) / b["h"], (cy + fh * 0.75 - b["y"]) / b["h"]
