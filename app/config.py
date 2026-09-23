from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINUTES_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    max_upload_mb: int = Field(default=200, ge=1, le=2048)
    stt_model_dir: Path = Path("models/whisper")
    diarization_model_dir: Path = Path("models/diarization")
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    grounded_extraction: bool = False
    exclusive_diarization: bool = False
    ffmpeg: str = "ffmpeg"
    device: str = "cpu"
    compute_type: str = "int8"
    stt_device: str | None = None
    stt_compute_type: str | None = None
    max_audio_seconds: int = Field(default=7200, ge=1, le=14400)
    pdf_font: Path = Path("static/fonts/DejaVuSans.ttf")

    @field_validator("ollama_url")
    @classmethod
    def local_ollama_only(cls, value: str) -> str:
        parsed = urlparse(value)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password):
            raise ValueError("Ollama must use an HTTP loopback address")
        return value
