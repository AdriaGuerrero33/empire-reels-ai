"""Proveedores de LLM para el análisis editorial (opcional).

El editor funciona sin ninguno ("heuristic"). Con Ollama todo es local y gratis.
Con OpenAI-compatible o Anthropic se registra el consumo real de tokens y el coste
estimado según los precios configurados.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from ..config import get_settings

DEFAULT_MODELS = {"ollama": "qwen3.5:4b", "openai": "gpt-4o-mini", "anthropic": "claude-haiku-5-5"}

PROMPT = """Eres editor jefe de vídeos cortos. Evalúa cada frase numerada de una transcripción en {lang}.
Para cada frase devuelve puntuaciones de 0 a 10:
- hook: potencia como gancho para abrir un vídeo corto (curiosidad, sorpresa, tensión).
- clarity: claridad del mensaje.
- autonomy: se entiende sin el contexto anterior.
- value: aporta un consejo, dato o explicación útil.
Y "labels": subconjunto de [question, surprise, tip, anecdote, explanation, cta, problem, solution, benefit, humor].
Y "broll": una búsqueda corta EN INGLÉS (2-4 palabras) de imagen de archivo que ilustre la frase sin
contradecirla, o "" si no procede (por ejemplo, frases abstractas o personales).
No inventes contenido. Responde SOLO con JSON: {{"items":[{{"id":0,"hook":7,"clarity":8,"autonomy":6,"value":5,"labels":["question"],"broll":"office paperwork"}}]}}

Frases:
{lines}"""


@dataclass
class LLMResult:
    items: dict[int, dict] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_eur: float = 0.0
    wall_s: float = 0.0
    provider: str = "heuristic"
    model: str = ""
    error: str = ""


def _extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Respuesta sin JSON")
    return json.loads(m.group(0))


def _call(provider: str, model: str, prompt: str) -> tuple[str, int, int]:
    s = get_settings()
    timeout = httpx.Timeout(s.llm_timeout_s, connect=10)
    if provider == "ollama":
        r = httpx.post(f"{s.ollama_url}/api/chat", timeout=timeout, json={
            "model": model, "stream": False, "format": "json", "think": False,
            "options": {"temperature": 0.1},
            "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        return d["message"]["content"], int(d.get("prompt_eval_count", 0)), int(d.get("eval_count", 0))
    if provider == "openai":
        r = httpx.post(f"{s.openai_base_url.rstrip('/')}/chat/completions", timeout=timeout,
                       headers={"Authorization": f"Bearer {s.openai_api_key}"},
                       json={"model": model, "temperature": 0.1, "response_format": {"type": "json_object"},
                             "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        u = d.get("usage", {})
        return d["choices"][0]["message"]["content"], int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
    if provider == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=timeout,
                       headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"},
                       json={"model": model, "max_tokens": 4096,
                             "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage", {})
        return text, int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
    raise ValueError(f"Proveedor desconocido: {provider}")


def provider_status() -> dict:
    s = get_settings()
    p = s.llm_provider
    ok = p == "heuristic" or (p == "ollama") or (p == "openai" and bool(s.openai_api_key)) or \
        (p == "anthropic" and bool(s.anthropic_api_key))
    return {"provider": p, "model": s.llm_model or DEFAULT_MODELS.get(p, ""), "configured": ok,
            "external_cost": p in ("openai", "anthropic")}


def refine_sentences(sentences: list[dict], lang: str, chunk: int = 40) -> LLMResult:
    s = get_settings()
    provider = s.llm_provider
    res = LLMResult(provider=provider, model=s.llm_model or DEFAULT_MODELS.get(provider, ""))
    if provider == "heuristic" or not sentences:
        return res
    if not provider_status()["configured"]:
        res.error = f"Proveedor {provider} sin clave configurada; se usa la heurística."
        return res
    lang_name = {"es": "español", "ca": "catalán", "en": "inglés"}.get(lang, lang)
    t0 = time.perf_counter()
    for k in range(0, len(sentences), chunk):
        part = sentences[k:k + chunk]
        lines = "\n".join(f"{x['id']}: {x['text']}" for x in part)
        prompt = PROMPT.format(lang=lang_name, lines=lines)
        try:
            text, tin, tout = _call(provider, res.model, prompt)
            res.tokens_in += tin
            res.tokens_out += tout
            data = _extract_json(text)
            for it in data.get("items", []):
                try:
                    res.items[int(it["id"])] = it
                except (KeyError, ValueError, TypeError):
                    continue
        except Exception as e:  # el análisis sigue con la heurística
            res.error = f"{type(e).__name__}: {str(e)[:200]}"
            break
    res.wall_s = round(time.perf_counter() - t0, 2)
    res.cost_eur = round(res.tokens_in / 1e6 * s.llm_price_in_per_mtok
                         + res.tokens_out / 1e6 * s.llm_price_out_per_mtok, 5)
    return res


def merge_llm(sentences: list[dict], llm: LLMResult, weight: float = 0.5) -> int:
    """Mezcla las puntuaciones del LLM con las heurísticas. Devuelve frases afectadas."""
    allowed = {"question", "surprise", "tip", "anecdote", "explanation", "cta", "problem", "solution",
               "benefit", "humor"}
    n = 0
    for s in sentences:
        it = llm.items.get(s["id"])
        if not it:
            continue
        n += 1
        sc = s["scores"]
        for key in ("hook", "clarity", "autonomy", "value"):
            try:
                v = max(0.0, min(10.0, float(it.get(key)))) / 10
            except (TypeError, ValueError):
                continue
            sc[key] = round((1 - weight) * sc[key] + weight * v, 3)
        sc["retention"] = round(0.45 * sc["hook"] + 0.3 * sc["value"] + 0.25 * sc["clarity"], 3)
        labs = [l for l in it.get("labels") or [] if l in allowed]
        s["labels"] = sorted(set(s["labels"]) | set(labs))
        for l in labs:  # que los pesos por etiqueta del planificador lo vean
            s["features"][l] = max(1, s["features"].get(l, 0))
        q = str(it.get("broll") or "").strip()
        if q:
            s["broll_query_en"] = q[:60]
        s["llm"] = True
    return n
