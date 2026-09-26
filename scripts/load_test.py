"""Concurrent load test against a running API.

    python -m scripts.load_test --requests 100 --concurrency 16

By default it cycles through the five acceptance fixtures, so after the first pass every
LLM call is a cache hit and the run measures the harness (queueing, embeddings, retrieval),
not model latency or spend. Pass --unique to make every request a new submission; that
makes real, paid model calls.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx

FIXTURES = list(json.loads(Path("tests/fixtures/submissions.json").read_text()).values())


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


async def run(url: str, total: int, concurrency: int, unique: bool, timeout: float) -> int:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: Counter[str] = Counter()
    llm_calls = cache_hits = 0
    cost = 0.0

    async def one(i: int, client: httpx.AsyncClient) -> None:
        nonlocal llm_calls, cache_hits, cost
        payload = dict(FIXTURES[i % len(FIXTURES)])
        if unique:
            payload["what_you_like"] = f"{payload['what_you_like']} (variant {uuid.uuid4().hex[:6]})"
        async with semaphore:
            start = time.perf_counter()
            try:
                response = await client.post(f"{url}/score", json=payload, headers={"x-request-id": f"load-{i}"})
            except httpx.HTTPError as exc:
                statuses[type(exc).__name__] += 1
                return
            latencies.append(time.perf_counter() - start)
            statuses[str(response.status_code)] += 1
            if response.status_code == 200:
                meta = response.json()["meta"]
                llm_calls += meta.get("llm_calls", 0)
                cache_hits += meta.get("llm_cache_hits", 0)
                cost += meta.get("estimated_cost_usd", 0.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        (await client.get(f"{url}/health")).raise_for_status()
        started = time.perf_counter()
        await asyncio.gather(*(one(i, client) for i in range(total)))
        elapsed = time.perf_counter() - started
        stats = (await client.get(f"{url}/stats")).json()

    ok = statuses.get("200", 0)
    print(f"requests={total} concurrency={concurrency} unique={unique} wall={elapsed:.2f}s throughput={total / elapsed:.1f} req/s")
    print(f"status counts: {dict(statuses)}")
    if latencies:
        print(f"client latency s: p50={percentile(latencies, .5):.3f} p95={percentile(latencies, .95):.3f} p99={percentile(latencies, .99):.3f} max={max(latencies):.3f}")
    print(f"upstream LLM calls={llm_calls} cache hits={cache_hits} estimated cost=${cost:.4f}")
    print("server /stats:")
    print(json.dumps({key: stats[key] for key in ("service", "llm", "embeddings_cache", "corpus")}, indent=2))
    return 0 if ok == total else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--unique", action="store_true", help="new submission per request (paid model calls)")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.url.rstrip("/"), args.requests, args.concurrency, args.unique, args.timeout)))


if __name__ == "__main__":
    main()
