"""Async OpenRouter JSON client: disk cache, in-flight de-duplication, concurrency limit,
circuit breaker, schema validation with one repair attempt, and usage accounting."""
import asyncio
import hashlib
import json
import logging
import os
import random
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar
from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel, ValidationError
from .config import Settings, get_settings
from .telemetry import USAGE_KEYS, record_usage, span

logger = logging.getLogger(__name__)
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
PARSE_ERRORS = (ValidationError, ValueError, json.JSONDecodeError)
RETRY_BASE_SECONDS = 0.5


class CircuitOpenError(RuntimeError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"LLM upstream circuit is open; retry in {retry_after:.0f}s.")
        self.retry_after = retry_after


class UpstreamError(RuntimeError):
    """The upstream model failed or never produced schema-valid output."""


class CircuitBreaker:
    """Closed → open after N consecutive upstream failures; after cooldown, one probe (half-open)."""

    def __init__(self, failure_threshold: int, cooldown_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.probe_in_flight = False
        self.times_opened = 0

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "half_open" if self.clock() - self.opened_at >= self.cooldown_seconds else "open"

    def before_call(self) -> None:
        state = self.state
        if state == "closed":
            return
        if state == "open" or self.probe_in_flight:
            raise CircuitOpenError(max(0.0, self.cooldown_seconds - (self.clock() - (self.opened_at or 0.0))) or 1.0)
        self.probe_in_flight = True

    def on_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None
        self.probe_in_flight = False

    def on_failure(self) -> None:
        self.consecutive_failures += 1
        was_probe = self.probe_in_flight
        self.probe_in_flight = False
        if was_probe or self.consecutive_failures >= self.failure_threshold:
            if self.opened_at is None or was_probe:
                self.times_opened += 1
            self.opened_at = self.clock()

    def snapshot(self) -> dict[str, Any]:
        return {"state": self.state, "consecutive_failures": self.consecutive_failures, "times_opened": self.times_opened}


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache_dir: Path = self.settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client: AsyncOpenAI | None = None
        self._semaphore = asyncio.Semaphore(self.settings.llm_max_concurrency)
        self._inflight: dict[Path, asyncio.Future[str]] = {}
        self.breaker = CircuitBreaker(self.settings.breaker_failure_threshold, self.settings.breaker_cooldown_seconds)
        self.metrics: dict[str, float] = {"calls": 0, "cache_hits": 0, "inflight_dedup": 0, "prompt_tokens": 0, "completion_tokens": 0, "estimated_cost_usd": 0.0, "upstream_failures": 0}

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self.settings.openrouter_api_key:
                raise UpstreamError("OPENROUTER_API_KEY is required for uncached LLM calls.")
            self._client = AsyncOpenAI(api_key=self.settings.openrouter_api_key.get_secret_value(), base_url=self.settings.openrouter_base_url, timeout=self.settings.llm_timeout_seconds, max_retries=0)
        return self._client

    def _cache_path(self, model: str, messages: list[dict[str, str]], schema: type[BaseModel], temperature: float) -> Path:
        payload = json.dumps({"model": model, "messages": messages, "schema": schema.model_json_schema(), "temperature": temperature}, sort_keys=True)
        return self.cache_dir / f"{hashlib.sha256(payload.encode()).hexdigest()}.json"

    def _write_cache(self, path: Path, content: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        os.replace(tmp, path)

    def _price(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        if model == self.settings.fast_model:
            input_rate, output_rate = self.settings.fast_input_usd_per_million, self.settings.fast_output_usd_per_million
        else:
            input_rate, output_rate = self.settings.judge_input_usd_per_million, self.settings.judge_output_usd_per_million
        return prompt_tokens * input_rate / 1_000_000 + completion_tokens * output_rate / 1_000_000

    def _count(self, **deltas: float) -> None:
        for key, value in deltas.items():
            self.metrics[key] += value
        record_usage(**{key: value for key, value in deltas.items() if key in USAGE_KEYS})

    async def _request(self, model: str, messages: list[dict[str, str]], temperature: float) -> str:
        client = self.client
        self.breaker.before_call()
        try:
            return await self._request_with_retries(client, model, messages, temperature)
        except asyncio.CancelledError:
            self.breaker.probe_in_flight = False
            raise

    async def _request_with_retries(self, client: AsyncOpenAI, model: str, messages: list[dict[str, str]], temperature: float) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                queued = time.perf_counter()
                async with self._semaphore:
                    with span("llm.request", model=model, attempt=attempt + 1, queue_ms=round((time.perf_counter() - queued) * 1000, 2)) as attrs:
                        response = await client.chat.completions.create(
                            model=model,
                            messages=messages,  # type: ignore[arg-type]
                            response_format={"type": "json_object"},
                            temperature=temperature,
                        )
                        usage = response.usage
                        prompt_tokens = (usage.prompt_tokens or 0) if usage else 0
                        completion_tokens = (usage.completion_tokens or 0) if usage else 0
                        attrs.update(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
                self._count(calls=1, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, estimated_cost_usd=self._price(model, prompt_tokens, completion_tokens))
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    raise UpstreamError("OpenRouter returned an empty response.")
                self.breaker.on_success()
                return content
            except APIStatusError as exc:
                last_error = exc
                if exc.status_code != 429 and exc.status_code < 500:
                    # The upstream answered, so it is reachable; client errors (bad model id, auth) must not trip the breaker.
                    self.breaker.on_success()
                    raise UpstreamError(f"OpenRouter rejected the request with HTTP {exc.status_code}.") from exc
            except UpstreamError as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
            if attempt < 2:
                await asyncio.sleep(RETRY_BASE_SECONDS * (2 ** attempt) + random.uniform(0, RETRY_BASE_SECONDS / 2))
        self.metrics["upstream_failures"] += 1
        self.breaker.on_failure()
        raise UpstreamError(f"OpenRouter request failed after 3 attempts: {type(last_error).__name__}") from last_error

    async def _fetch(self, cache_path: Path, model: str, messages: list[dict[str, str]], temperature: float) -> tuple[str, bool]:
        """Return (content, from_cache). Concurrent identical uncached prompts share one upstream call."""
        if cache_path.exists():
            self._count(cache_hits=1)
            return cache_path.read_text(), True
        pending = self._inflight.get(cache_path)
        if pending is not None:
            try:
                content = await asyncio.shield(pending)
                self._count(inflight_dedup=1)
                return content, True
            except asyncio.CancelledError:
                if not pending.cancelled():
                    raise
                # The owning request was cancelled; make the call ourselves.
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._inflight[cache_path] = future
        try:
            content = await self._request(model, messages, temperature)
            future.set_result(content)
            return content, False
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved so a failure with no waiters does not log a warning
            raise
        finally:
            self._inflight.pop(cache_path, None)

    @staticmethod
    def _validate(content: str, response_model: type[ResponseModel], check: Callable[[ResponseModel], None] | None) -> ResponseModel:
        raw = json.loads(content)
        if isinstance(raw, list) and "reviews" in response_model.model_fields:
            raw = {"reviews": raw}
        parsed = response_model.model_validate(raw)
        if check is not None:
            check(parsed)
        return parsed

    async def complete_json(self, *, model: str, system: str, prompt: str, response_model: type[ResponseModel], temperature: float = 0, check: Callable[[ResponseModel], None] | None = None, span_name: str = "llm.complete_json") -> ResponseModel:
        """`check` may raise ValueError for semantic problems (e.g. missing batch ids); that triggers the repair prompt."""
        models = [model]
        if self.settings.fallback_model and self.settings.fallback_model != model:
            models.append(self.settings.fallback_model)
        last_error: Exception | None = None
        with span(span_name, schema=response_model.__name__) as attrs:
            for parse_attempt in range(2):
                repair = f"\n\nYour previous response failed validation: {last_error}. Return corrected JSON only." if parse_attempt else ""
                for active_model in models:
                    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt + repair}]
                    cache_path = self._cache_path(active_model, messages, response_model, temperature)
                    try:
                        content, cached = await self._fetch(cache_path, active_model, messages, temperature)
                    except (UpstreamError, CircuitOpenError) as exc:
                        last_error = exc
                        logger.error("llm_model_failed model=%s error=%s", active_model, type(exc).__name__)
                        if isinstance(exc, CircuitOpenError):
                            raise
                        continue
                    try:
                        parsed = self._validate(content, response_model, check)
                    except PARSE_ERRORS as exc:
                        last_error = exc
                        if cached:
                            cache_path.unlink(missing_ok=True)
                        logger.warning("llm_structured_output_invalid model=%s schema=%s attempt=%d", active_model, response_model.__name__, parse_attempt + 1)
                        continue
                    if not cached:
                        self._write_cache(cache_path, parsed.model_dump_json(indent=2))
                    attrs.update(model=active_model, cached=cached, repaired=bool(parse_attempt))
                    return parsed
                if last_error is not None and not isinstance(last_error, PARSE_ERRORS):
                    break
        raise UpstreamError(f"LLM response did not match {response_model.__name__}: {last_error}") from last_error

    def snapshot(self) -> dict[str, Any]:
        lookups = self.metrics["calls"] + self.metrics["cache_hits"] + self.metrics["inflight_dedup"]
        return {
            **{key: (round(value, 6) if isinstance(value, float) else value) for key, value in self.metrics.items()},
            "cache_hit_rate": round((self.metrics["cache_hits"] + self.metrics["inflight_dedup"]) / lookups, 4) if lookups else None,
            "max_concurrency": self.settings.llm_max_concurrency,
            "circuit_breaker": self.breaker.snapshot(),
        }
