"""B-roll desde fuentes con licencia de uso libre (Pexels, Pixabay).

Comprobación de derechos: solo se aceptan recursos de proveedores cuya licencia
permite uso comercial sin atribución obligatoria; se guarda proveedor, autor, URL
y licencia en el plan para el registro de créditos. Si no hay claves o no hay un
resultado pertinente, se devuelve None y el plan usa el vídeo original o un
recurso gráfico interno.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx

from ..config import get_settings

LICENSES = {
    "pexels": {"name": "Pexels License", "url": "https://www.pexels.com/license/", "commercial": True},
    "pixabay": {"name": "Pixabay Content License", "url": "https://pixabay.com/service/license-summary/",
                "commercial": True},
}
LOCALES = {"es": ("es-ES", "es"), "ca": ("es-ES", "es"), "en": ("en-US", "en")}
MAX_BYTES = 60 * 1024 * 1024


def available() -> list[str]:
    s = get_settings()
    return [p for p, k in (("pexels", s.pexels_api_key), ("pixabay", s.pixabay_api_key)) if k]


def _stems(words: list[str]) -> set[str]:
    return {w.lower()[:5] for w in words if len(w) >= 4}


def _relevant(query_words: list[str], text: str) -> bool:
    """El recurso debe compartir al menos una raíz con la búsqueda (evita imágenes ajenas al discurso)."""
    toks = re.findall(r"[a-zà-ÿ]+", text.lower())
    return bool(_stems(query_words) & {t[:5] for t in toks if len(t) >= 4})


def _search_pexels(q: str, lang: str, portrait: bool) -> list[dict]:
    s = get_settings()
    loc = LOCALES.get(lang, LOCALES["es"])[0]
    out = []
    with httpx.Client(timeout=20, headers={"Authorization": s.pexels_api_key}) as c:
        r = c.get("https://api.pexels.com/videos/search", params={
            "query": q, "per_page": 8, "orientation": "portrait" if portrait else "landscape",
            "size": "medium", "locale": loc})
        if r.status_code == 200:
            for v in r.json().get("videos", []):
                files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                         and f.get("height")]
                if not files:
                    continue
                files.sort(key=lambda f: abs((f.get("height") or 0) - (1920 if portrait else 1080)))
                slug = v.get("url", "")
                out.append({"provider": "pexels", "kind": "video", "url": files[0]["link"],
                            "page": slug, "author": (v.get("user") or {}).get("name", ""),
                            "text": slug.replace("-", " "), "duration": v.get("duration")})
        r = c.get("https://api.pexels.com/v1/search", params={
            "query": q, "per_page": 8, "orientation": "portrait" if portrait else "landscape", "locale": loc})
        if r.status_code == 200:
            for p in r.json().get("photos", []):
                out.append({"provider": "pexels", "kind": "image", "url": p["src"].get("large2x") or p["src"]["original"],
                            "page": p.get("url", ""), "author": p.get("photographer", ""),
                            "text": (p.get("alt") or "") + " " + p.get("url", "").replace("-", " ")})
    return out


def _search_pixabay(q: str, lang: str, portrait: bool) -> list[dict]:
    s = get_settings()
    lg = LOCALES.get(lang, LOCALES["es"])[1]
    out = []
    with httpx.Client(timeout=20) as c:
        r = c.get("https://pixabay.com/api/videos/", params={"key": s.pixabay_api_key, "q": q, "lang": lg,
                                                             "per_page": 8, "safesearch": "true"})
        if r.status_code == 200:
            for h in r.json().get("hits", []):
                v = (h.get("videos") or {}).get("medium") or (h.get("videos") or {}).get("small")
                if v and v.get("url"):
                    out.append({"provider": "pixabay", "kind": "video", "url": v["url"], "page": h.get("pageURL", ""),
                                "author": h.get("user", ""), "text": h.get("tags", ""), "duration": h.get("duration")})
        r = c.get("https://pixabay.com/api/", params={"key": s.pixabay_api_key, "q": q, "lang": lg,
                                                      "image_type": "photo", "safesearch": "true", "per_page": 8,
                                                      "orientation": "vertical" if portrait else "horizontal"})
        if r.status_code == 200:
            for h in r.json().get("hits", []):
                out.append({"provider": "pixabay", "kind": "image", "url": h.get("largeImageURL"),
                            "page": h.get("pageURL", ""), "author": h.get("user", ""), "text": h.get("tags", "")})
    return out


def _download(url: str, dst: Path) -> bool:
    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as r:
            if r.status_code != 200:
                return False
            n = 0
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    n += len(chunk)
                    if n > MAX_BYTES:
                        f.close()
                        dst.unlink(missing_ok=True)
                        return False
                    f.write(chunk)
        return True
    except httpx.HTTPError:
        dst.unlink(missing_ok=True)
        return False


def find(query_words: list[str], lang: str, portrait: bool, exclude: set[str] | None = None,
         query_en: str | None = None, prefer: str = "video") -> dict | None:
    """Busca, comprueba pertinencia y licencia, descarga y cachea. Devuelve el recurso o None."""
    providers = available()
    if not providers or not (query_words or query_en):
        return None
    s = get_settings()
    q_native = " ".join(query_words[:3])
    attempts = [(query_en, "en", query_en.split())] if query_en else []
    if q_native:
        attempts.append((q_native, lang, query_words))
    exclude = exclude or set()
    cache_root = s.cache_dir / "broll"
    for q, lg, qwords in attempts:
        key = hashlib.sha1(f"{q}|{lg}|{portrait}".encode()).hexdigest()[:16]
        meta_path = cache_root / f"{key}.json"
        if meta_path.exists():
            results = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            results = []
            for p in providers:
                try:
                    results += _search_pexels(q, lg, portrait) if p == "pexels" else _search_pixabay(q, lg, portrait)
                except httpx.HTTPError:
                    continue
            meta_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        results = [r for r in results if r.get("url") and r["url"] not in exclude
                   and LICENSES.get(r["provider"], {}).get("commercial") and _relevant(qwords, r.get("text", ""))]
        results.sort(key=lambda r: 0 if r["kind"] == prefer else 1)
        for r in results:
            ext = ".mp4" if r["kind"] == "video" else ".jpg"
            fname = hashlib.sha1(r["url"].encode()).hexdigest()[:20] + ext
            dst = cache_root / fname
            if not dst.exists() and not _download(r["url"], dst):
                continue
            lic = LICENSES[r["provider"]]
            return {"path": f"cache/broll/{fname}", "kind": r["kind"], "provider": r["provider"],
                    "author": r.get("author", ""), "page": r.get("page", ""), "source_url": r["url"],
                    "license": lic["name"], "license_url": lic["url"], "query": q}
    return None
