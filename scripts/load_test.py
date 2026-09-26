"""Cold vs warm load test for POST /score.

    .venv/bin/python -m scripts.load_test            # writes reports/load.md

Starts its own API server per phase so the cache flag is controlled here, not by clients:
  cold: CACHE_ENABLED=false (no LLM response cache, no in-flight de-dup, no embedding cache)
  warm: CACHE_ENABLED=true, primed with one unmeasured pass over the same submissions
Each phase runs the same 20 labelled submissions (4 per eval category) at concurrency 1, 5 and 10.

Live spend is capped (default $0.50). The script stops dispatching once spend plus the worst-case
cost of requests still in flight would exceed the cap, and passes the remaining budget to the server
as LLM_BUDGET_USD so the server itself degrades instead of overspending.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests/fixtures/eval_cases.json").read_text())
REPORT = ROOT / "reports/load.md"
FIELDS = ("what_you_like", "what_you_dislike", "problem_solved")
INITIAL_COST_GUESS = 0.01  # per request, until real costs are observed


def pick_submissions(n: int) -> list[dict[str, str]]:
    by_category: dict[str, list[dict]] = {}
    for case in CASES:
        by_category.setdefault(case["category"], []).append(case)
    ordered = [case for group in zip(*by_category.values()) for case in group]
    return [{key: case[key] for key in FIELDS} for case in ordered[:n]]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


class Budget:
    def __init__(self, cap: float) -> None:
        self.cap = cap
        self.spent = 0.0
        self.in_flight = 0
        self.max_seen = INITIAL_COST_GUESS
        self.exhausted = False

    def can_dispatch(self) -> bool:
        if self.spent + (self.in_flight + 1) * self.max_seen > self.cap:
            self.exhausted = True
        return not self.exhausted

    def settle(self, cost: float) -> None:
        self.spent += cost
        self.max_seen = max(self.max_seen, cost)


@dataclass
class RunResult:
    phase: str
    concurrency: int
    planned: int
    latencies_ms: list[float] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)
    degraded: int = 0
    cost: float = 0.0
    llm_calls: int = 0
    cache_hits: int = 0
    wall_s: float = 0.0
    aborted: bool = False

    @property
    def sent(self) -> int:
        return sum(self.statuses.values())

    @property
    def errors(self) -> int:
        return self.sent - self.statuses.get("200", 0)


async def run_level(url: str, phase: str, submissions: list[dict], concurrency: int, budget: Budget | None, timeout: float) -> RunResult:
    result = RunResult(phase=phase, concurrency=concurrency, planned=len(submissions))
    queue: asyncio.Queue[tuple[int, dict]] = asyncio.Queue()
    for item in enumerate(submissions):
        queue.put_nowait(item)

    async def worker(client: httpx.AsyncClient) -> None:
        while not queue.empty():
            if budget is not None and not budget.can_dispatch():
                result.aborted = True
                return
            i, payload = queue.get_nowait()
            if budget is not None:
                budget.in_flight += 1
            started = time.perf_counter()
            cost = 0.0
            try:
                response = await client.post(f"{url}/score", json=payload, headers={"x-request-id": f"load-{phase}-c{concurrency}-{i}"})
                key = str(response.status_code)
                if response.status_code == 200:
                    meta = response.json()["meta"]
                    cost = meta["total_cost"]
                    result.cost += cost
                    result.llm_calls += meta["llm_calls"]
                    result.cache_hits += meta["cache_hits"]
                    result.degraded += int(meta["degraded"])
            except httpx.HTTPError as exc:
                key = type(exc).__name__
            finally:
                if budget is not None:
                    budget.in_flight -= 1
                    budget.settle(cost)
            result.latencies_ms.append((time.perf_counter() - started) * 1000)
            result.statuses[key] = result.statuses.get(key, 0) + 1

    async with httpx.AsyncClient(timeout=timeout) as client:
        started = time.perf_counter()
        await asyncio.gather(*(worker(client) for _ in range(concurrency)))
        result.wall_s = time.perf_counter() - started
    return result


class Server:
    def __init__(self, port: int, env: dict[str, str]) -> None:
        self.url = f"http://127.0.0.1:{port}"
        self.log = open(ROOT / "logs" / f"load_server_{port}.log", "w")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env={**os.environ, **env}, stdout=self.log, stderr=subprocess.STDOUT)

    async def wait_ready(self, timeout: float = 180) -> None:
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=2) as client:
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"server exited early; see {self.log.name}")
                try:
                    if (await client.get(f"{self.url}/health")).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        raise TimeoutError("server did not become healthy")

    async def stats(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            return (await client.get(f"{self.url}/stats")).json()

    def stop(self) -> None:
        self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


async def phase(name: str, cache_enabled: bool, port: int, submissions: list[dict], levels: list[int], budget: Budget, timeout: float) -> tuple[list[RunResult], dict, float]:
    remaining = max(0.0, budget.cap - budget.spent)
    server = Server(port, {"CACHE_ENABLED": str(cache_enabled).lower(), "LLM_BUDGET_USD": f"{remaining:.4f}", "MAX_INFLIGHT_REQUESTS": "64", "TRACE_LOG_PATH": str(ROOT / "logs" / "load_traces.jsonl")})
    prime_cost = 0.0
    try:
        await server.wait_ready()
        if cache_enabled:
            prime = await run_level(server.url, f"{name}-prime", submissions, max(levels), budget, timeout)
            prime_cost = prime.cost
            print(f"[{name}] primed cache: {prime.sent} requests, ${prime.cost:.4f}")
        results = []
        for level in levels:
            if budget.exhausted:
                break
            result = await run_level(server.url, name, submissions, level, budget, timeout)
            results.append(result)
            print(f"[{name}] c={level}: sent={result.sent} p50={percentile(result.latencies_ms, .5):.0f}ms p95={percentile(result.latencies_ms, .95):.0f}ms errors={result.errors} degraded={result.degraded} cost=${result.cost:.4f} spent_total=${budget.spent:.4f}")
        return results, await server.stats(), prime_cost
    finally:
        server.stop()


def fmt(value: float | None, digits: int = 0) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def write_report(results: list[RunResult], stats: dict[str, dict], budget: Budget, prime_cost: float, args: argparse.Namespace) -> None:
    lines = [
        "# Load test: POST /score",
        "",
        f"Generated by `scripts/load_test.py`. {args.requests} labelled submissions per level (4 each of novel+relevant, redundant, paraphrase, off-topic, gibberish), sequential levels at concurrency {', '.join(map(str, args.concurrency))}. Latency is client-side wall time per request.",
        "",
        "- **cold**: server started with `CACHE_ENABLED=false`: no LLM response cache, no in-flight de-duplication, no embedding cache. Every request makes real model calls.",
        "- **warm**: server with caches on, primed by one unmeasured pass over the same submissions.",
        "",
        "| Phase | Concurrency | Requests | p50 ms | p95 ms | Error rate | Degraded | Cost / request | LLM calls / request | Throughput req/s |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        sent = result.sent or 1
        lines.append(f"| {result.phase} | {result.concurrency} | {result.sent}{' (aborted)' if result.aborted else ''} | {fmt(percentile(result.latencies_ms, .5))} | {fmt(percentile(result.latencies_ms, .95))} | {result.errors / sent:.1%} | {result.degraded} | ${result.cost / sent:.5f} | {result.llm_calls / sent:.1f} | {result.sent / result.wall_s if result.wall_s else 0:.2f} |")
    lines += ["", f"Total live spend: **${budget.spent:.4f}** of the ${budget.cap:.2f} cap (warm-cache priming: ${prime_cost:.4f}).{' Stopped early: the spend cap was reached.' if budget.exhausted else ''}", ""]
    for name, snapshot in stats.items():
        llm = snapshot.get("llm", {})
        lines.append(f"Server `/stats` after **{name}**: {snapshot.get('request_count')} requests, p50 {fmt(snapshot.get('latency_ms', {}).get('p50'))} ms, p95 {fmt(snapshot.get('latency_ms', {}).get('p95'))} ms, cost ${snapshot.get('total_cost_usd', 0):.4f}, cache hit rate {snapshot.get('cache_hit_rate')}, degraded {snapshot.get('degraded_count')}, retries {llm.get('retries')}, breaker {llm.get('circuit_breaker', {}).get('state')}, served models {llm.get('served_models')}.")
        lines.append("")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print(f"\nWrote {REPORT.relative_to(ROOT)}")


async def main_async(args: argparse.Namespace) -> int:
    (ROOT / "logs").mkdir(exist_ok=True)
    submissions = pick_submissions(args.requests)
    budget = Budget(args.cap)
    results: list[RunResult] = []
    stats: dict[str, dict] = {}
    prime_cost = 0.0
    phases = [("cold", False), ("warm", True)] if not args.warm_only else [("warm", True)]
    for offset, (name, cache_enabled) in enumerate(phases):
        if budget.exhausted:
            break
        phase_results, stats[name], primed = await phase(name, cache_enabled, args.port + offset, submissions, args.concurrency, budget, args.timeout)
        results += phase_results
        prime_cost += primed
    write_report(results, stats, budget, prime_cost, args)
    return 0 if all(result.errors == 0 for result in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=lambda value: [int(item) for item in value.split(",")], default=[1, 5, 10])
    parser.add_argument("--cap", type=float, default=0.50, help="maximum live spend in USD for the whole run")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--warm-only", action="store_true", help="skip the paid cold phase")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
