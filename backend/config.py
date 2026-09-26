from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openrouter_api_key: SecretStr | None = Field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    frontend_origin: str = "http://localhost:3000"
    fast_model: str = "google/gemini-2.5-flash-lite"
    judge_model: str = "google/gemini-2.5-flash"
    high_threshold: float = 0.75
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
    entailment_top_k: int = Field(default=3, ge=1, le=10)
    partial_novelty_credit: float = Field(default=0.5, ge=0, le=1)
    llm_max_concurrency: int = Field(default=8, ge=1)
    max_inflight_requests: int = Field(default=32, ge=1)
    breaker_failure_threshold: int = Field(default=5, ge=1)
    breaker_cooldown_seconds: float = Field(default=30.0, gt=0)
    embedding_cache_size: int = Field(default=4096, ge=0)

@lru_cache
def get_settings() -> Settings:
    return Settings()
