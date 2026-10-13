"""Análisis visual: cambios de escena (PySceneDetect) y seguimiento de caras (YuNet, OpenCV)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parent.parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"


def detect_scenes(video: Path, threshold: float = 27.0) -> list[dict]:
    from scenedetect import ContentDetector, detect
    scenes = detect(str(video), ContentDetector(threshold=threshold, min_scene_len=12))
    return [{"start": round(a.get_seconds(), 3), "end": round(b.get_seconds(), 3)} for a, b in scenes]


def track_faces(video: Path, step_s: float = 0.4, on_progress=None) -> dict:
    """Muestrea fotogramas y detecta caras. Devuelve muestras normalizadas (0-1).

    Cada muestra: {t, faces:[{cx,cy,w,h,score}]} ordenadas por tamaño (la mayor es el
    protagonista probable). El seguimiento se suaviza en el planificador por plano.
    """
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return {"samples": [], "error": "No se pudo abrir el vídeo"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = 640 / max(w, h) if max(w, h) > 640 else 1.0
    dw, dh = int(w * scale), int(h * scale)
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (dw, dh), 0.7, 0.3, 50)
    step = max(1, int(round(fps * step_s)))
    samples = []
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            if scale != 1.0:
                frame = cv2.resize(frame, (dw, dh))
            _, faces = det.detect(frame)
            fl = []
            if faces is not None:
                for f in faces:
                    x, y, fw, fh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
                    fl.append({"cx": round((x + fw / 2) / dw, 4), "cy": round((y + fh / 2) / dh, 4),
                               "w": round(fw / dw, 4), "h": round(fh / dh, 4), "score": round(score, 3)})
                fl.sort(key=lambda d: d["w"] * d["h"], reverse=True)
            samples.append({"t": round(idx / fps, 3), "faces": fl[:4]})
            if on_progress and n_frames:
                on_progress(min(0.99, idx / n_frames))
        idx += 1
    cap.release()
    with_face = sum(1 for s in samples if s["faces"])
    return {"samples": samples, "step_s": step_s, "face_ratio": round(with_face / max(1, len(samples)), 3)}


def face_center(track: dict, start: float, end: float) -> dict | None:
    """Centro robusto (mediana) del protagonista en un intervalo, más su deriva."""
    pts = [s["faces"][0] for s in track.get("samples", []) if start <= s["t"] <= end and s["faces"]]
    if len(pts) < 2:
        # Ventana ampliada si el plano es muy corto
        pts = [s["faces"][0] for s in track.get("samples", [])
               if start - 1.5 <= s["t"] <= end + 1.5 and s["faces"]]
        if not pts:
            return None
    cx = np.array([p["cx"] for p in pts])
    cy = np.array([p["cy"] for p in pts])
    fh = np.array([p["h"] for p in pts])
    fw = np.array([p["w"] for p in pts])
    first = pts[: max(1, len(pts) // 3)]
    last = pts[-max(1, len(pts) // 3):]
    return {"cx": float(np.median(cx)), "cy": float(np.median(cy)), "h": float(np.median(fh)),
            "w": float(np.median(fw)),
            "cx_start": float(np.median([p["cx"] for p in first])),
            "cx_end": float(np.median([p["cx"] for p in last])),
            "spread": float(np.std(cx)), "n": len(pts)}
