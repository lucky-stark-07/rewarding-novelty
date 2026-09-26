"""OpenRouter JSON client with cache, schema validation, retries, and usage counters."""
import logging
import hashlib
import json
import time
from pathlib import Path
from typing import Any, TypeVar
from pydantic import BaseModel, ValidationError
from openai import OpenAI, APIStatusError
from .config import Settings, get_settings

logger = logging.getLogger(__name__)
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache_dir: Path = self.settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client: OpenAI | None = None
        self.metrics = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0, "estimated_cost_usd": 0.0}

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self.settings.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY is required for uncached LLM calls.")
            self._client = OpenAI(api_key=self.settings.openrouter_api_key, base_url=self.settings.openrouter_base_url, timeout=self.settings.llm_timeout_seconds, max_retries=0)
        return self._client

    def _cache_path(self, model: str, messages: list[dict[str, str]], schema: type[BaseModel], temperature: float) -> Path:
        payload = json.dumps({"model": model, "messages": messages, "schema": schema.model_json_schema(), "temperature": temperature}, sort_keys=True)
        return self.cache_dir / f"{hashlib.sha256(payload.encode()).hexdigest()}.json"

    def _price(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        if model == self.settings.fast_model:
            input_rate, output_rate = self.settings.fast_input_usd_per_million, self.settings.fast_output_usd_per_million
        else:
            input_rate, output_rate = self.settings.judge_input_usd_per_million, self.settings.judge_output_usd_per_million
        return prompt_tokens * input_rate / 1_000_000 + completion_tokens * output_rate / 1_000_000

    def _request(self, model: str, messages: list[dict[str, str]], temperature: float) -> tuple[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    response_format={"type": "json_object"},
                    temperature=temperature,
                )
                self.metrics["calls"] += 1
                usage = response.usage
                if usage:
                    prompt_tokens, completion_tokens = usage.prompt_tokens or 0, usage.completion_tokens or 0
                    self.metrics["prompt_tokens"] += prompt_tokens
                    self.metrics["completion_tokens"] += completion_tokens
                    self.metrics["estimated_cost_usd"] += self._price(model, prompt_tokens, completion_tokens)
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("OpenRouter returned an empty response.")
                return content, response
            except APIStatusError as exc:
                last_error = exc
                if exc.status_code != 429 and exc.status_code < 500:
                    raise
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
            except Exception as exc:
                # Network errors are retried; schema and JSON parsing happen outside this method.
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"OpenRouter request failed after 3 attempts: {last_error}") from last_error

    @staticmethod
    def _validate(content: str, response_model: type[ResponseModel]) -> ResponseModel:
        raw = json.loads(content)
        if isinstance(raw, list) and "reviews" in response_model.model_fields:
            raw = {"reviews": raw}
        return response_model.model_validate(raw)

    def complete_json(self, *, model: str, system: str, prompt: str, response_model: type[ResponseModel], temperature: float = 0) -> ResponseModel:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        models = [model]
        if self.settings.fallback_model and self.settings.fallback_model != model:
            models.append(self.settings.fallback_model)
        last_parse_error: Exception | None = None
        for parse_attempt in range(2):
            repair = ""
            if parse_attempt:
                repair = f"\n\nYour previous response failed schema validation: {last_parse_error}. Return corrected JSON only."
            for active_model in models:
                active_messages = [dict(messages[0]), {"role": "user", "content": prompt + repair}]
                cache_path = self._cache_path(active_model, active_messages, response_model, temperature)
                if cache_path.exists():
                    self.metrics["cache_hits"] += 1
                    try:
                        return self._validate(cache_path.read_text(), response_model)
                    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                        cache_path.unlink(missing_ok=True)
                        last_parse_error = exc
                        continue
                try:
                    content, _ = self._request(active_model, active_messages, temperature)
                except Exception as exc:
                    last_parse_error = exc
                    logger.error("llm_model_failed", extra={"model": active_model, "error_type": type(exc).__name__})
                    continue
                try:
                    parsed = self._validate(content, response_model)
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    last_parse_error = exc
                    logger.warning("llm_structured_output_invalid", extra={"model": active_model, "response_schema": response_model.__name__, "attempt": parse_attempt + 1})
                    continue
                cache_path.write_text(parsed.model_dump_json(indent=2))
                return parsed
            if last_parse_error and not isinstance(last_parse_error, (ValidationError, json.JSONDecodeError)):
                break
        raise ValueError(f"OpenRouter response did not match {response_model.__name__}: {last_parse_error}") from last_parse_error
