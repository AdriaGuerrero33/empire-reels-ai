"""Utilidades FFmpeg/FFprobe.

Seguridad: todos los procesos se lanzan con lista de argumentos (nunca shell=True)
y las rutas las genera el servidor. Ningún texto del usuario entra en un grafo de
filtros: los textos van en ficheros .ass escapados.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import get_settings

# Contenedores aceptados según ffprobe (no según la extensión del fichero).
ALLOWED_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi", "mpegts",
                   "flv", "mxf"}


class MediaError(Exception):
    pass


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    wall_s: float
    cpu_s: float


def run(cmd: list[str], timeout: int | None = None,
        on_progress: Callable[[float], None] | None = None, total_s: float | None = None,
        cwd: Path | None = None) -> ProcResult:
    """Ejecuta un proceso midiendo tiempo real y de CPU. Lanza MediaError si falla."""
    try:
        import psutil  # opcional
    except ImportError:  # pragma: no cover
        psutil = None
    t0 = time.perf_counter()
    if on_progress and total_s and cmd and Path(cmd[0]).stem.startswith("ffmpeg"):
        cmd = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace",
                            cwd=str(cwd) if cwd else None)
    ps = None
    cpu = 0.0
    if psutil:
        try:
            ps = psutil.Process(proc.pid)
        except Exception:
            ps = None
    out_lines: list[str] = []
    import threading
    err_chunks: list[str] = []

    def _drain_err():
        for line in proc.stderr:  # type: ignore[union-attr]
            err_chunks.append(line)
            if len(err_chunks) > 4000:
                del err_chunks[:2000]

    th = threading.Thread(target=_drain_err, daemon=True)
    th.start()
    deadline = t0 + timeout if timeout else None
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            out_lines.append(line)
            if ps is not None:
                try:
                    t = ps.cpu_times()
                    cpu = t.user + t.system
                except Exception:
                    pass
            if on_progress and total_s and line.startswith("out_time_us="):
                try:
                    us = int(line.split("=", 1)[1])
                    on_progress(max(0.0, min(1.0, us / 1e6 / total_s)))
                except ValueError:
                    pass
            if deadline and time.perf_counter() > deadline:
                proc.kill()
                raise MediaError(f"Tiempo agotado ({timeout}s) en {Path(cmd[0]).name}")
        proc.wait(timeout=max(1, (deadline - time.perf_counter())) if deadline else None)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise MediaError(f"Tiempo agotado ({timeout}s) en {Path(cmd[0]).name}")
    th.join(timeout=5)
    wall = time.perf_counter() - t0
    stderr = "".join(err_chunks)
    res = ProcResult(proc.returncode, "".join(out_lines), stderr, wall, cpu)
    if proc.returncode != 0:
        tail = "\n".join(stderr.strip().splitlines()[-12:])
        raise MediaError(f"{Path(cmd[0]).name} falló (código {proc.returncode}):\n{tail}")
    return res


def ffprobe(path: Path) -> dict:
    s = get_settings()
    res = run([s.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format",
               "-show_streams", str(path)], timeout=120)
    return json.loads(res.stdout or "{}")


def describe(path: Path) -> dict:
    """Valida un vídeo y devuelve metadatos normalizados."""
    try:
        info = ffprobe(path)
    except MediaError as e:
        raise MediaError("El archivo no es un vídeo legible por FFmpeg.") from e
    fmt = info.get("format", {})
    names = set((fmt.get("format_name") or "").split(","))
    if not names & ALLOWED_FORMATS:
        raise MediaError(f"Formato contenedor no admitido: {fmt.get('format_name')}")
    vstreams = [st for st in info.get("streams", []) if st.get("codec_type") == "video"
                and st.get("disposition", {}).get("attached_pic", 0) == 0]
    astreams = [st for st in info.get("streams", []) if st.get("codec_type") == "audio"]
    if not vstreams:
        raise MediaError("El archivo no contiene pista de vídeo.")
    v = vstreams[0]
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if (v.get("tags") or {}).get("rotate"):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    fr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"
    try:
        num, den = fr.split("/")
        fps = float(num) / float(den) if float(den) else 30.0
    except Exception:
        fps = 30.0
    duration = float(fmt.get("duration") or v.get("duration") or 0)
    if w <= 0 or h <= 0 or duration <= 0:
        raise MediaError("No se pudo determinar resolución o duración del vídeo.")
    return {
        "width": w, "height": h, "fps": round(fps, 3), "duration": duration,
        "vcodec": v.get("codec_name"), "acodec": astreams[0].get("codec_name") if astreams else None,
        "has_audio": bool(astreams), "format": fmt.get("format_name"), "rotation": rot,
        "size_bytes": int(fmt.get("size") or path.stat().st_size),
        "orientation": "vertical" if h > w else ("square" if h == w else "horizontal"),
    }


def extract_audio(src: Path, dst: Path) -> ProcResult:
    s = get_settings()
    return run([s.ffmpeg_bin, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(dst)], timeout=s.render_timeout_s)


def make_proxy(src: Path, dst: Path, height: int = 540, on_progress=None, duration=None) -> ProcResult:
    """Proxy ligero (para análisis visual y previsualización en el editor)."""
    s = get_settings()
    return run([s.ffmpeg_bin, "-y", "-v", "error", "-i", str(src),
                "-vf", f"scale=-2:{height}:flags=fast_bilinear,fps=30", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "30", "-g", "30", "-c:a", "aac", "-b:a", "96k",
                "-ac", "2", "-movflags", "+faststart", str(dst)],
               timeout=s.render_timeout_s, on_progress=on_progress, total_s=duration)


SIL_START = re.compile(r"silence_start: (-?[\d.]+)")
SIL_END = re.compile(r"silence_end: (-?[\d.]+) \| silence_duration: ([\d.]+)")


def detect_silences(audio: Path, noise_db: float = -35.0, min_dur: float = 0.3) -> list[dict]:
    s = get_settings()
    res = run([s.ffmpeg_bin, "-v", "info", "-i", str(audio), "-af",
               f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"], timeout=600)
    out, start = [], None
    for line in res.stderr.splitlines():
        m = SIL_START.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = SIL_END.search(line)
        if m and start is not None:
            out.append({"start": round(start, 3), "end": round(float(m.group(1)), 3)})
            start = None
    return out


def thumbnail(src: Path, at: float, dst: Path, width: int = 360) -> None:
    s = get_settings()
    run([s.ffmpeg_bin, "-y", "-v", "error", "-ss", f"{max(0, at):.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-q:v", "4", str(dst)], timeout=120)


def mean_volume(path: Path) -> float | None:
    s = get_settings()
    try:
        res = run([s.ffmpeg_bin, "-v", "info", "-i", str(path), "-vn", "-af", "volumedetect",
                   "-f", "null", "-"], timeout=600)
    except MediaError:
        return None
    m = re.search(r"mean_volume: (-?[\d.]+) dB", res.stderr)
    return float(m.group(1)) if m else None


def validate_output(path: Path, expect_w: int, expect_h: int, expect_dur: float) -> dict:
    """Comprobación real del MP4 renderizado: pistas, tamaño, duración y audio no mudo."""
    checks: dict = {"ok": False, "problems": []}
    if not path.exists() or path.stat().st_size < 1024:
        checks["problems"].append("El archivo de salida no existe o está vacío.")
        return checks
    info = ffprobe(path)
    v = [st for st in info.get("streams", []) if st.get("codec_type") == "video"]
    a = [st for st in info.get("streams", []) if st.get("codec_type") == "audio"]
    dur = float(info.get("format", {}).get("duration") or 0)
    checks.update({"duration": round(dur, 2), "has_video": bool(v), "has_audio": bool(a),
                   "width": int(v[0]["width"]) if v else 0, "height": int(v[0]["height"]) if v else 0,
                   "vcodec": v[0].get("codec_name") if v else None, "size_bytes": path.stat().st_size})
    if not v:
        checks["problems"].append("Sin pista de vídeo.")
    if not a:
        checks["problems"].append("Sin pista de audio.")
    if v and (checks["width"], checks["height"]) != (expect_w, expect_h):
        checks["problems"].append(f"Resolución {checks['width']}x{checks['height']} ≠ {expect_w}x{expect_h}.")
    if abs(dur - expect_dur) > max(0.6, expect_dur * 0.03):
        checks["problems"].append(f"Duración {dur:.2f}s distinta de la planificada {expect_dur:.2f}s.")
    if a:
        mv = mean_volume(path)
        checks["mean_volume_db"] = mv
        if mv is not None and mv < -55:
            checks["problems"].append("El audio parece mudo.")
    checks["ok"] = not checks["problems"]
    return checks
