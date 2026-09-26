"""Per-request trace spans and process-wide service statistics."""
from __future__ import annotations

import time
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

USAGE_KEYS = ("calls", "cache_hits", "prompt_tokens", "completion_tokens", "estimated_cost_usd")


class RequestTrace:
    """Spans and LLM usage for one request; shared by tasks spawned from it via contextvars."""

    def __init__(self, request_id: str | None = None) -> None:
        self.request_id = request_id
        self.started = time.perf_counter()
        self.spans: list[dict[str, Any]] = []
        self.usage: dict[str, float] = {key: 0 for key in USAGE_KEYS}

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        start = time.perf_counter()
        record: dict[str, Any] = {"name": name, "start_ms": round((start - self.started) * 1000, 2), "duration_ms": 0.0, "attrs": attrs}
        try:
            yield attrs
        except BaseException as exc:
            attrs["error"] = type(exc).__name__
            raise
        finally:
            record["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            self.spans.append(record)

    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.started

    def sorted_spans(self) -> list[dict[str, Any]]:
        return sorted(self.spans, key=lambda item: item["start_ms"])


current_trace: ContextVar[RequestTrace | None] = ContextVar("current_trace", default=None)


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Record a span on the active request trace; a no-op outside a request."""
    trace = current_trace.get()
    if trace is None:
        yield attrs
        return
    with trace.span(name, **attrs) as live_attrs:
        yield live_attrs


def record_usage(**deltas: float) -> None:
    trace = current_trace.get()
    if trace is not None:
        for key, value in deltas.items():
            trace.usage[key] += value


class ServiceStats:
    """In-memory counters for GET /stats. Single-process; resets on restart."""

    def __init__(self, window: int = 1000) -> None:
        self.started = time.time()
        self.requests = 0
        self.in_flight = 0
        self.rejected = 0
        self.outcomes: Counter[str] = Counter()
        self.latencies: deque[float] = deque(maxlen=window)
        self.stage_totals: Counter[str] = Counter()

    def record(self, outcome: str, latency_seconds: float, spans: list[dict[str, Any]] | None = None) -> None:
        self.requests += 1
        self.outcomes[outcome] += 1
        self.latencies.append(latency_seconds)
        for item in spans or []:
            self.stage_totals[item["name"]] += item["duration_ms"]

    def latency_summary(self) -> dict[str, float | None]:
        if not self.latencies:
            return {"p50": None, "p95": None, "p99": None, "max": None}
        ordered = sorted(self.latencies)
        pick = lambda q: round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 4)
        return {"p50": pick(0.50), "p95": pick(0.95), "p99": pick(0.99), "max": round(ordered[-1], 4)}

    def snapshot(self) -> dict[str, Any]:
        uptime = time.time() - self.started
        return {
            "uptime_seconds": round(uptime, 1),
            "requests_total": self.requests,
            "requests_in_flight": self.in_flight,
            "requests_rejected_overload": self.rejected,
            "outcomes": dict(self.outcomes),
            "latency_seconds": self.latency_summary(),
            "latency_window": len(self.latencies),
            "mean_stage_ms": {name: round(total / max(self.outcomes["ok"], 1), 2) for name, total in self.stage_totals.items()},
        }
