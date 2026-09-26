"""Contextvars-based span tracer, JSONL trace sink, and process-wide service statistics."""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Span:
    name: str
    start_ms: float
    attrs: dict[str, Any]
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    cache_hits: int = 0
    served_models: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        used_llm = self.llm_calls + self.cache_hits > 0
        return {
            "name": self.name,
            "start_ms": round(self.start_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "tokens": self.prompt_tokens + self.completion_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            "cache_hit": (self.llm_calls == 0) if used_llm else None,
            "served_model": ",".join(sorted(self.served_models)) or None,
            "attrs": self.attrs,
        }


class RequestTrace:
    """One request's spans and totals. Tasks spawned from the request share it through contextvars."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex
        self.started = time.perf_counter()
        self.spans: list[Span] = []
        self.totals = Span(name="request", start_ms=0.0, attrs={})
        self.degraded_reasons: list[str] = []

    def degrade(self, reason: str) -> None:
        if reason not in self.degraded_reasons:
            self.degraded_reasons.append(reason)

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_reasons)

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000

    def span_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in sorted(self.spans, key=lambda item: item.start_ms)]


current_trace: ContextVar[RequestTrace | None] = ContextVar("current_trace", default=None)
_open_spans: ContextVar[tuple[Span, ...]] = ContextVar("open_spans", default=())


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Time a block as a span on the active trace (a no-op outside a request). Yields mutable attrs."""
    trace = current_trace.get()
    if trace is None:
        yield attrs
        return
    record = Span(name=name, start_ms=trace.elapsed_ms(), attrs=attrs)
    token = _open_spans.set((*_open_spans.get(), record))
    started = time.perf_counter()
    try:
        yield attrs
    except BaseException as exc:
        attrs["error"] = type(exc).__name__
        raise
    finally:
        record.duration_ms = (time.perf_counter() - started) * 1000
        _open_spans.reset(token)
        trace.spans.append(record)


def record_llm(*, prompt_tokens: int = 0, completion_tokens: int = 0, cached_tokens: int = 0, cost_usd: float = 0.0, calls: int = 0, cache_hits: int = 0, served_model: str | None = None) -> None:
    """Attribute LLM usage to the request totals and to every span currently open in this task."""
    trace = current_trace.get()
    if trace is None:
        return
    for target in (trace.totals, *_open_spans.get()):
        target.prompt_tokens += prompt_tokens
        target.completion_tokens += completion_tokens
        target.cached_tokens += cached_tokens
        target.cost_usd += cost_usd
        target.llm_calls += calls
        target.cache_hits += cache_hits
        if served_model:
            target.served_models.add(served_model)


class TraceSink:
    """Appends one JSON line per span to a file; safe across threads."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, trace: RequestTrace, **request_fields: Any) -> None:
        if self.path is None:
            return
        now = time.time()
        lines = [json.dumps({"ts": now, "trace_id": trace.trace_id, **request_fields, **item}, sort_keys=True) for item in trace.span_dicts()]
        with self._lock, open(self.path, "a") as handle:
            handle.write("\n".join(lines) + "\n")


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


class ServiceStats:
    """In-memory counters for GET /stats. Single-process; resets on restart."""

    def __init__(self, window: int = 2000) -> None:
        self.started = time.time()
        self.request_count = 0
        self.in_flight = 0
        self.rejected = 0
        self.degraded_count = 0
        self.total_cost_usd = 0.0
        self.llm_calls = 0
        self.cache_hits = 0
        self.outcomes: Counter[str] = Counter()
        self.masked: Counter[str] = Counter()
        self.moderation: Counter[str] = Counter()
        self.latencies_ms: deque[float] = deque(maxlen=window)

    def record(self, outcome: str, latency_ms: float, trace: RequestTrace | None = None) -> None:
        self.request_count += 1
        self.outcomes[outcome] += 1
        self.latencies_ms.append(latency_ms)
        if trace is not None:
            self.total_cost_usd += trace.totals.cost_usd
            self.llm_calls += trace.totals.llm_calls
            self.cache_hits += trace.totals.cache_hits
            self.degraded_count += int(trace.degraded)

    def snapshot(self) -> dict[str, Any]:
        latencies = list(self.latencies_ms)
        lookups = self.llm_calls + self.cache_hits
        pick = lambda q: round(value, 2) if (value := percentile(latencies, q)) is not None else None
        return {
            "request_count": self.request_count,
            "latency_ms": {"p50": pick(0.50), "p95": pick(0.95), "p99": pick(0.99), "window": len(latencies)},
            "total_cost_usd": round(self.total_cost_usd, 6),
            "cache_hit_rate": round(self.cache_hits / lookups, 4) if lookups else None,
            "degraded_count": self.degraded_count,
            "llm_calls": self.llm_calls,
            "llm_cache_hits": self.cache_hits,
            "outcomes": dict(self.outcomes),
            "guardrails": {"masked_by_type": dict(self.masked), "moderation": dict(self.moderation)},
            "in_flight": self.in_flight,
            "rejected_overload": self.rejected,
            "uptime_seconds": round(time.time() - self.started, 1),
        }
