from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openrouter_api_key: SecretStr | None = Field(default=None, repr=False)
    # POST /corpus/regenerate replaces the whole corpus and makes paid calls: disabled unless this is set.
    admin_token: SecretStr | None = Field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    frontend_origin: str = "http://localhost:3000"
    fast_model: str = "google/gemini-2.5-flash-lite"
    judge_model: str = "google/gemini-2.5-flash"
    # Comma-separated; sent to OpenRouter as extra_body.models so it fails over server-side.
    fast_model_fallbacks: str = ""
    judge_model_fallbacks: str = ""
    # Moderation guard: any OpenAI-compatible endpoint. Unset URL/key fall back to OpenRouter; point
    # GUARD_BASE_URL at an on-prem server (vLLM, Ollama, TGI) to keep review text in-house.
    moderation_enabled: bool = True
    guard_base_url: str | None = None
    guard_api_key: SecretStr | None = Field(default=None, repr=False)
    guard_model: str = "google/gemini-2.5-flash-lite"
    high_threshold: float = 0.75
    low_threshold: float = 0.35
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    cache_dir: Path = Path("backend/.cache")
    corpus_path: Path = Path("backend/corpus.json")
    trace_log_path: Path | None = Path("logs/traces.jsonl")
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
    llm_max_attempts: int = Field(default=3, ge=1)
    llm_max_retry_after_seconds: float = Field(default=20.0, ge=0)
    max_inflight_requests: int = Field(default=32, ge=1)
    breaker_failure_threshold: int = Field(default=3, ge=1)
    breaker_cooldown_seconds: float = Field(default=30.0, gt=0)
    # Lifetime upstream spend cap for this process; once reached, scoring degrades to embedding-only.
    llm_budget_usd: float | None = Field(default=None, ge=0)
    # Degraded mode only: a claim counts as relevant when its cosine similarity to the reference text reaches this.
    # On the eval set, relevant claims average 0.19 and off-topic/gibberish 0.04; 0.10 keeps ~80% / rejects ~80%.
    degraded_relevance_threshold: float = Field(default=0.10, ge=-1, le=1)
    cache_enabled: bool = True
    llm_memory_cache_size: int = Field(default=1024, ge=0)
    embedding_cache_size: int = Field(default=4096, ge=0)

    @field_validator("trace_log_path", mode="before")
    @classmethod
    def _empty_path_disables_tracing(cls, value: object) -> object:
        # TRACE_LOG_PATH= (empty) would otherwise become Path(".") and fail on every write.
        return None if isinstance(value, str) and not value.strip() else value

    def guard_settings(self) -> "Settings":
        """Settings for the guard's own LLM client: separate endpoint, key, breaker and cache namespace."""
        return self.model_copy(update={
            "openrouter_base_url": self.guard_base_url or self.openrouter_base_url,
            "openrouter_api_key": self.guard_api_key or self.openrouter_api_key,
            "fast_model": self.guard_model,
            "fast_model_fallbacks": "",
        })

    def fallbacks_for(self, model: str) -> list[str]:
        raw = self.fast_model_fallbacks if model == self.fast_model else self.judge_model_fallbacks if model == self.judge_model else ""
        return [item for item in _split(raw) if item != model]


@lru_cache
def get_settings() -> Settings:
    return Settings()
