"""Configuración central. Todo se lee de variables de entorno (o de backend/.env).

Las claves de API nunca se devuelven por la API: solo se informa de si están
configuradas.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ROOT_DIR / "data" / "secrets.env"),
        env_prefix="ER_",
        extra="ignore",
    )

    # Almacenamiento y base de datos
    data_dir: Path = ROOT_DIR / "data"
    database_url: str = ""  # vacío => SQLite en data_dir/empire.db

    # API
    api_token: str = ""  # si se define, todas las rutas exigen Bearer / ?token=
    cors_origins: str = "http://localhost:3090,http://127.0.0.1:3090"
    embedded_worker: bool = True  # en desarrollo, el API arranca su propio worker

    # Límites de seguridad
    max_upload_mb: int = 2048
    max_duration_s: int = 3 * 3600
    min_duration_s: float = 3.0

    # Transcripción
    whisper_model: str = "small"
    whisper_device: str = "auto"  # auto | cpu | cuda
    whisper_compute_type: str = "auto"  # auto => int8 en CPU, float16 en GPU

    # Análisis editorial con LLM (opcional). heuristic | ollama | openai | anthropic
    llm_provider: str = "heuristic"
    llm_model: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_price_in_per_mtok: float = 0.0  # € por millón de tokens de entrada (para estimar coste)
    llm_price_out_per_mtok: float = 0.0
    llm_timeout_s: int = 240

    # B-roll (opcional, gratuitos con clave)
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    # Render
    worker_concurrency: int = 2  # renders simultáneos por worker
    analysis_concurrency: int = 1
    x264_preset: str = "veryfast"
    x264_crf: int = 20
    preview_height: int = 960
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    render_timeout_s: int = 3600
    keep_temp: bool = False
    job_max_attempts: int = 2
    job_stale_after_s: int = 300  # latido perdido => el trabajo se reencola

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'empire.db').as_posix()}"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def fonts_dir(self) -> Path:
        return BACKEND_DIR / "app" / "assets" / "fonts"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.projects_dir, self.cache_dir, self.library_dir,
                  self.library_dir / "music", self.library_dir / "logos", self.cache_dir / "broll"):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
