from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openrouter_api_key: str | None = Field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    frontend_origin: str = "http://localhost:3000"
    fast_model: str = "google/gemini-2.5-flash-lite"
    judge_model: str = "google/gemini-2.5-flash"
    high_threshold: float = 0.65
    low_threshold: float = 0.35
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    cache_dir: Path = Path("backend/.cache")
    corpus_path: Path = Path("backend/corpus.json")
    fallback_model: str | None = None
    llm_timeout_seconds: float = 45.0
    max_field_length: int = 4000
    corpus_acceptance_threshold: float = 0.60
    fast_input_usd_per_million: float = 0.10
    fast_output_usd_per_million: float = 0.40
    judge_input_usd_per_million: float = 0.30
    judge_output_usd_per_million: float = 2.50

@lru_cache
def get_settings() -> Settings:
    return Settings()
