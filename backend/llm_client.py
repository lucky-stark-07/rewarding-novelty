"""Async OpenRouter JSON client.

Layers, outermost first: response cache (in-memory LRU → disk) with in-flight de-duplication,
budget cap and circuit breaker, global concurrency semaphore, tenacity retries (timeouts, 429,
5xx; honours Retry-After), then one Pydantic validation with a single repair re-ask."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import tempfile
import time
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, TypeVar
from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt
from .config import Settings, get_settings
from .prompts import Prompt
from .telemetry import record_llm, span

logger = logging.getLogger(__name__)
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
PARSE_ERRORS = (ValidationError, ValueError, json.JSONDecodeError)
RETRY_BASE_SECONDS = 0.5
RETRY_MAX_BACKOFF_SECONDS = 8.0


class UpstreamError(RuntimeError):
    """The model call failed, or never produced schema-valid output."""


class CircuitOpenError(RuntimeError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"LLM circuit is open; retry in {retry_after:.0f}s.")
        self.retry_after = retry_after


class BudgetExceededError(RuntimeError):
    pass


LLM_UNAVAILABLE = (UpstreamError, CircuitOpenError, BudgetExceededError)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, APIConnectionError):  # includes APITimeoutError
        return True
    return isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500)


def retry_after_seconds(exc: BaseException | None) -> float | None:
    if not isinstance(exc, APIStatusError):
        return None
    headers = exc.response.headers
    if (value := headers.get("retry-after-ms")) is not None:
        try:
            return max(0.0, float(value) / 1000)
        except ValueError:
            pass
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return None


class CircuitBreaker:
    """Closed → open after N consecutive failed calls; after the cooldown one probe (half-open) decides."""

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
            raise CircuitOpenError(max(1.0, self.cooldown_seconds - (self.clock() - (self.opened_at or 0.0))))
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


@dataclass
class CallResult:
    content: str
    cached: bool
    served_model: str | None


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache_dir: Path = self.settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client: AsyncOpenAI | None = None
        self._semaphore = asyncio.Semaphore(self.settings.llm_max_concurrency)
        self._inflight: dict[str, asyncio.Future[CallResult]] = {}
        self._memory: OrderedDict[str, tuple[str, str | None]] = OrderedDict()
        self.breaker = CircuitBreaker(self.settings.breaker_failure_threshold, self.settings.breaker_cooldown_seconds)
        self.served_models: Counter[str] = Counter()
        self.metrics: dict[str, float] = {"calls": 0, "attempts": 0, "retries": 0, "memory_hits": 0, "disk_hits": 0, "inflight_dedup": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0, "upstream_failures": 0, "repairs": 0}

    @property
    def cache_enabled(self) -> bool:
        return self.settings.cache_enabled

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self.settings.openrouter_api_key:
                raise UpstreamError("OPENROUTER_API_KEY is required for uncached LLM calls.")
            self._client = AsyncOpenAI(api_key=self.settings.openrouter_api_key.get_secret_value(), base_url=self.settings.openrouter_base_url, timeout=self.settings.llm_timeout_seconds, max_retries=0)
        return self._client

    # ---- cache -------------------------------------------------------------------------------

    @staticmethod
    def cache_key(model: str, prompt_version: str, temperature: float, response_model: type[BaseModel], messages: list[dict[str, str]]) -> str:
        schema_hash = hashlib.sha256(json.dumps(response_model.model_json_schema(), sort_keys=True).encode()).hexdigest()
        payload = json.dumps({"model": model, "prompt_version": prompt_version, "temperature": temperature, "schema_hash": schema_hash, "messages": messages}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _disk_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _remember(self, key: str, value: tuple[str, str | None]) -> None:
        if self.settings.llm_memory_cache_size <= 0:
            return
        self._memory[key] = value
        self._memory.move_to_end(key)
        while len(self._memory) > self.settings.llm_memory_cache_size:
            self._memory.popitem(last=False)

    def _cache_get(self, key: str) -> tuple[str, str | None] | None:
        if (hit := self._memory.get(key)) is not None:
            self._memory.move_to_end(key)
            self.metrics["memory_hits"] += 1
            return hit
        path = self._disk_path(key)
        if not path.exists():
            return None
        try:
            stored = json.loads(path.read_text())
            value = (stored["content"], stored.get("served_model"))
        except (json.JSONDecodeError, KeyError, TypeError):
            path.unlink(missing_ok=True)
            return None
        self.metrics["disk_hits"] += 1
        self._remember(key, value)
        return value

    def _cache_put(self, key: str, content: str, served_model: str | None) -> None:
        self._remember(key, (content, served_model))
        fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            json.dump({"served_model": served_model, "content": content}, handle)
        os.replace(tmp, self._disk_path(key))

    def _cache_drop(self, key: str) -> None:
        self._memory.pop(key, None)
        self._disk_path(key).unlink(missing_ok=True)

    # ---- upstream ----------------------------------------------------------------------------

    def _price(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        if model == self.settings.fast_model:
            input_rate, output_rate = self.settings.fast_input_usd_per_million, self.settings.fast_output_usd_per_million
        else:
            input_rate, output_rate = self.settings.judge_input_usd_per_million, self.settings.judge_output_usd_per_million
        return prompt_tokens * input_rate / 1_000_000 + completion_tokens * output_rate / 1_000_000

    def _wait(self, retry_state: RetryCallState) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        hinted = retry_after_seconds(exc)
        if hinted is not None:
            return min(hinted, self.settings.llm_max_retry_after_seconds)
        backoff = min(RETRY_MAX_BACKOFF_SECONDS, RETRY_BASE_SECONDS * 2 ** (retry_state.attempt_number - 1))
        return backoff + random.uniform(0, RETRY_BASE_SECONDS)

    def _check_budget(self) -> None:
        budget = self.settings.llm_budget_usd
        if budget is not None and self.metrics["cost_usd"] >= budget:
            raise BudgetExceededError(f"LLM budget of ${budget:.2f} reached (spent ${self.metrics['cost_usd']:.4f}).")

    async def _create_once(self, client: AsyncOpenAI, model: str, messages: list[dict[str, str]], temperature: float, attempt: int) -> tuple[str, str | None]:
        extra_body: dict[str, Any] = {"usage": {"include": True}}
        fallbacks = self.settings.fallbacks_for(model)
        if fallbacks:
            extra_body["models"] = [model, *fallbacks]
        queued = time.perf_counter()
        async with self._semaphore:
            with span("llm.call", model=model, attempt=attempt, queue_ms=round((time.perf_counter() - queued) * 1000, 2)) as attrs:
                self.metrics["attempts"] += 1
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    extra_body=extra_body,
                )
                served_model = getattr(response, "model", None) or None
                usage = response.usage
                prompt_tokens = (usage.prompt_tokens or 0) if usage else 0
                completion_tokens = (usage.completion_tokens or 0) if usage else 0
                details = getattr(usage, "prompt_tokens_details", None) if usage else None
                cached_tokens = (getattr(details, "cached_tokens", 0) or 0) if details else 0
                reported = getattr(usage, "cost", None) if usage else None
                cost = float(reported) if isinstance(reported, (int, float)) else self._price(model, prompt_tokens, completion_tokens)
                attrs.update(served_model=served_model, cost_source="reported" if isinstance(reported, (int, float)) else "estimated")
                self.metrics["calls"] += 1
                self.metrics["prompt_tokens"] += prompt_tokens
                self.metrics["completion_tokens"] += completion_tokens
                self.metrics["cached_tokens"] += cached_tokens
                self.metrics["cost_usd"] += cost
                if served_model:
                    self.served_models[served_model] += 1
                record_llm(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cached_tokens=cached_tokens, cost_usd=cost, calls=1, served_model=served_model)
        logger.info("llm_call requested_model=%s served_model=%s prompt_tokens=%d completion_tokens=%d cached_tokens=%d cost_usd=%.6f", model, served_model, prompt_tokens, completion_tokens, cached_tokens, cost)
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise UpstreamError("OpenRouter returned an empty response.")
        return content, served_model

    async def _call_upstream(self, model: str, messages: list[dict[str, str]], temperature: float) -> CallResult:
        try:
            self._check_budget()
            client = self.client
        except UpstreamError:
            self.breaker.on_failure()
            raise
        self.breaker.before_call()
        try:
            async for attempt in AsyncRetrying(stop=stop_after_attempt(self.settings.llm_max_attempts), wait=self._wait, retry=retry_if_exception(is_retryable), reraise=True):
                with attempt:
                    if attempt.retry_state.attempt_number > 1:
                        self.metrics["retries"] += 1
                    content, served_model = await self._create_once(client, model, messages, temperature, attempt.retry_state.attempt_number)
        except asyncio.CancelledError:
            self.breaker.probe_in_flight = False
            raise
        except Exception as exc:
            self.metrics["upstream_failures"] += 1
            self.breaker.on_failure()
            logger.error("llm_call_failed model=%s error=%s", model, type(exc).__name__)
            if isinstance(exc, UpstreamError):
                raise
            raise UpstreamError(f"OpenRouter request failed: {type(exc).__name__}") from exc
        self.breaker.on_success()
        return CallResult(content=content, cached=False, served_model=served_model)

    async def _fetch(self, key: str, model: str, messages: list[dict[str, str]], temperature: float) -> CallResult:
        if not self.cache_enabled:
            return await self._call_upstream(model, messages, temperature)
        if (hit := self._cache_get(key)) is not None:
            record_llm(cache_hits=1, served_model=hit[1])
            return CallResult(content=hit[0], cached=True, served_model=hit[1])
        pending = self._inflight.get(key)
        if pending is not None:
            try:
                result = await asyncio.shield(pending)
                self.metrics["inflight_dedup"] += 1
                record_llm(cache_hits=1, served_model=result.served_model)
                return CallResult(content=result.content, cached=True, served_model=result.served_model)
            except asyncio.CancelledError:
                if not pending.cancelled():
                    raise
                # The owning request was cancelled; make the call ourselves.
        future: asyncio.Future[CallResult] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            result = await self._call_upstream(model, messages, temperature)
            future.set_result(result)
            return result
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved so a failure with no waiters does not log a warning
            raise
        finally:
            self._inflight.pop(key, None)

    # ---- public API --------------------------------------------------------------------------

    @staticmethod
    def _validate(content: str, response_model: type[ResponseModel], check: Callable[[ResponseModel], None] | None) -> ResponseModel:
        raw = json.loads(content)
        if isinstance(raw, list) and "reviews" in response_model.model_fields:
            raw = {"reviews": raw}
        parsed = response_model.model_validate(raw)
        if check is not None:
            check(parsed)
        return parsed

    async def complete_json(self, prompt: Prompt, *, model: str, variables: dict[str, Any], response_model: type[ResponseModel], temperature: float = 0, check: Callable[[ResponseModel], None] | None = None) -> ResponseModel:
        """Render `prompt`, call `model`, and return validated output.

        `check` may raise ValueError for semantic problems (e.g. missing batch ids). Any validation
        failure triggers exactly one repair re-ask that includes the error. Raises one of
        LLM_UNAVAILABLE when no valid output can be obtained."""
        user = prompt.render(**variables)
        last_error: Exception | None = None
        for parse_attempt in range(2):
            content = user if not parse_attempt else f"{user}\n\nYour previous response failed validation: {last_error}\nReturn corrected JSON only."
            messages = [{"role": "system", "content": prompt.system}, {"role": "user", "content": content}]
            key = self.cache_key(model, prompt.PROMPT_VERSION, temperature, response_model, messages)
            result = await self._fetch(key, model, messages, temperature)
            try:
                parsed = self._validate(result.content, response_model, check)
            except PARSE_ERRORS as exc:
                last_error = exc
                if result.cached:
                    self._cache_drop(key)
                if not parse_attempt:
                    self.metrics["repairs"] += 1
                logger.warning("llm_structured_output_invalid prompt=%s model=%s attempt=%d error=%s", prompt.PROMPT_VERSION, model, parse_attempt + 1, str(exc)[:200])
                continue
            if not result.cached and self.cache_enabled:
                self._cache_put(key, parsed.model_dump_json(), result.served_model)
            return parsed
        raise UpstreamError(f"{prompt.PROMPT_VERSION} output did not match {response_model.__name__} after one repair: {last_error}") from last_error

    def snapshot(self) -> dict[str, Any]:
        hits = self.metrics["memory_hits"] + self.metrics["disk_hits"] + self.metrics["inflight_dedup"]
        lookups = hits + self.metrics["calls"]
        return {
            **{key: (round(value, 6) if isinstance(value, float) else value) for key, value in self.metrics.items()},
            "cache_enabled": self.cache_enabled,
            "cache_hit_rate": round(hits / lookups, 4) if lookups else None,
            "memory_cache_entries": len(self._memory),
            "served_models": dict(self.served_models),
            "max_concurrency": self.settings.llm_max_concurrency,
            "budget_usd": self.settings.llm_budget_usd,
            "circuit_breaker": self.breaker.snapshot(),
        }
