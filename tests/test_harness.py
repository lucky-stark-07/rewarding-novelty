import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from pydantic import BaseModel
from backend import llm_client as llm_module
from backend.config import Settings
from backend.corpus import CorpusIndex, CorpusStore
from backend.embeddings import embed
from backend.llm_client import CircuitBreaker, CircuitOpenError, LLMClient, UpstreamError
from backend.main import create_app
from backend.routes import submit as submit_route
from backend.schemas import Claim, CorpusEntry, FieldName, Submission
from tests.conftest import FixtureLLM


class Answer(BaseModel):
    value: int


class FakeCompletions:
    """Stands in for AsyncOpenAI.chat.completions; records peak concurrency."""

    def __init__(self, contents: list[str] | None = None, fail: bool = False, delay: float = 0.02) -> None:
        self.contents = contents
        self.fail = fail
        self.delay = delay
        self.calls = 0
        self.active = 0
        self.peak = 0

    async def create(self, **_kwargs):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise ConnectionError("upstream down")
            content = self.contents.pop(0) if self.contents else json.dumps({"value": 1})
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5), choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        finally:
            self.active -= 1


def make_client(tmp_path: Path, fake: FakeCompletions, **overrides) -> LLMClient:
    client = LLMClient(Settings(cache_dir=tmp_path / "cache", openrouter_api_key="test-key", **overrides))
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))  # type: ignore[assignment]
    return client


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "RETRY_BASE_SECONDS", 0.0)


def ask(client: LLMClient, prompt: str, **kwargs):
    return client.complete_json(model="m", system="s", prompt=prompt, response_model=Answer, **kwargs)


def test_llm_concurrency_is_bounded_by_semaphore(tmp_path: Path) -> None:
    fake = FakeCompletions()
    async def run():
        client = make_client(tmp_path, fake, llm_max_concurrency=3)
        await asyncio.gather(*(ask(client, f"prompt {i}") for i in range(20)))
    asyncio.run(run())
    assert fake.calls == 20
    assert fake.peak <= 3


def test_identical_concurrent_prompts_share_one_upstream_call_then_hit_cache(tmp_path: Path) -> None:
    fake = FakeCompletions()
    async def run():
        client = make_client(tmp_path, fake)
        results = await asyncio.gather(*(ask(client, "same") for _ in range(10)))
        await ask(client, "same")
        return client, results
    client, results = asyncio.run(run())
    assert fake.calls == 1
    assert all(result.value == 1 for result in results)
    assert client.metrics["inflight_dedup"] == 9 and client.metrics["cache_hits"] == 1


def test_schema_check_failure_triggers_one_repair_prompt(tmp_path: Path) -> None:
    fake = FakeCompletions(contents=[json.dumps({"value": 7}), json.dumps({"value": 1})])
    def must_be_one(answer: Answer) -> None:
        if answer.value != 1:
            raise ValueError("value must be 1")
    result = asyncio.run(ask(make_client(tmp_path, fake), "repair me", check=must_be_one))
    assert result.value == 1 and fake.calls == 2


def test_circuit_opens_after_repeated_failures_and_fails_fast(tmp_path: Path) -> None:
    fake = FakeCompletions(fail=True, delay=0)
    async def run():
        client = make_client(tmp_path, fake, breaker_failure_threshold=2)
        for i in range(2):
            with pytest.raises(UpstreamError):
                await ask(client, f"p{i}")
        calls_before = fake.calls
        with pytest.raises(CircuitOpenError):
            await ask(client, "p-open")
        return client, calls_before
    client, calls_before = asyncio.run(run())
    assert calls_before == 6  # 2 requests × 3 attempts
    assert fake.calls == calls_before
    assert client.breaker.state == "open"


def test_circuit_breaker_half_open_probe_closes_on_success() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10, clock=lambda: now[0])
    breaker.on_failure()
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
    now[0] = 11
    assert breaker.state == "half_open"
    breaker.before_call()  # the single probe is admitted
    with pytest.raises(CircuitOpenError):
        breaker.before_call()  # concurrent callers still fail fast
    breaker.on_success()
    assert breaker.state == "closed"


def test_circuit_breaker_failed_probe_reopens() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=10, clock=lambda: now[0])
    for _ in range(3):
        breaker.on_failure()
    now[0] = 11
    breaker.before_call()
    breaker.on_failure()
    assert breaker.state == "open" and breaker.times_opened == 2


def test_missing_api_key_does_not_trip_breaker(tmp_path: Path) -> None:
    client = LLMClient(Settings(cache_dir=tmp_path / "cache", openrouter_api_key=None))
    for i in range(6):
        with pytest.raises(UpstreamError):
            asyncio.run(ask(client, f"k{i}"))
    assert client.breaker.state == "closed"


def test_settings_never_expose_api_key() -> None:
    settings = Settings(openrouter_api_key="sk-or-secret-value")
    assert "sk-or-secret-value" not in repr(settings)
    assert "sk-or-secret-value" not in str(settings.model_dump())


def _entry(i: int) -> CorpusEntry:
    return CorpusEntry(id=f"e{i}", submission=Submission(what_you_like=f"Distinct observation number {i}."), claims=[Claim(id=f"c{i}", field=FieldName.WHAT_YOU_LIKE, text=f"Distinct observation number {i}.")])


def test_concurrent_corpus_appends_do_not_lose_entries(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    threads = [threading.Thread(target=CorpusStore(path).append, args=(_entry(i),)) for i in range(25)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(entry.id for entry in CorpusStore(path).list()) == sorted(f"e{i}" for i in range(25))


def test_corpus_index_add_updates_retrieval_and_duplicates(tmp_path: Path) -> None:
    async def run():
        index = await CorpusIndex.create(CorpusStore(tmp_path / "corpus.json"), embed)
        await index.add(_entry(1))
        await index.add(_entry(1))
        vector = embed(["Distinct observation number 1."])[0]
        return index, index.neighbors(FieldName.WHAT_YOU_LIKE, vector, 3)
    index, neighbors = asyncio.run(run())
    assert len(index.entries) == 1 and index.claim_count == 1
    assert neighbors[0][1] == pytest.approx(1.0, abs=1e-4)
    assert index.find_duplicate(Submission(what_you_like="  distinct OBSERVATION number 1. ")) is not None


# ---- API ----

def app_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(corpus_path=tmp_path / "corpus.json", cache_dir=tmp_path / "cache", **overrides)


async def with_app(settings: Settings, llm, fn):
    app = create_app(settings, llm=llm)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await fn(app, client)


def test_score_route_returns_request_meta_trace_and_structured_log(tmp_path: Path, caplog) -> None:
    import logging
    caplog.set_level(logging.INFO, logger="rewarding_novelty.requests")
    async def fn(_app, client):
        return await client.post("/score", headers={"x-request-id": "test-request-123"}, json={"what_you_like": "Useful", "what_you_dislike": "Slow", "problem_solved": "Planning"})
    response = asyncio.run(with_app(app_settings(tmp_path), FixtureLLM(), fn))
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["request_id"] == "test-request-123" == response.headers["x-request-id"]
    assert any(span["name"] == "llm.extract_claims" or span["name"] == "judge.batch" for span in body["meta"]["trace"])
    log_record = next(record for record in caplog.records if record.name == "rewarding_novelty.requests")
    logged = json.loads(log_record.message)
    assert logged["request_id"] == "test-request-123" and "trace" not in logged


def test_score_route_rejects_overlong_field(tmp_path: Path) -> None:
    async def fn(_app, client):
        return await client.post("/score", json={"what_you_like": "x" * 4001})
    assert asyncio.run(with_app(app_settings(tmp_path), FixtureLLM(), fn)).status_code == 422


def test_overload_is_shed_with_503(tmp_path: Path) -> None:
    async def fn(app, client):
        app.state.stats.in_flight = app.state.settings.max_inflight_requests
        response = await client.post("/score", json={"what_you_like": "Useful"})
        app.state.stats.in_flight = 0
        stats = (await client.get("/stats")).json()
        return response, stats
    response, stats = asyncio.run(with_app(app_settings(tmp_path, max_inflight_requests=2), FixtureLLM(), fn))
    assert response.status_code == 503 and response.headers["retry-after"] == "1"
    assert stats["service"]["requests_rejected_overload"] == 1


@pytest.mark.parametrize("error, status", [(CircuitOpenError(12.2), 503), (UpstreamError("bad json"), 502)])
def test_upstream_failures_map_to_clean_http_errors(tmp_path: Path, monkeypatch, error, status) -> None:
    async def failing(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(submit_route, "score_submission", failing)
    async def fn(_app, client):
        return await client.post("/score", json={"what_you_like": "Useful"}), (await client.get("/stats")).json()
    response, stats = asyncio.run(with_app(app_settings(tmp_path), FixtureLLM(), fn))
    assert response.status_code == status
    if status == 503:
        assert response.headers["retry-after"] == "13"
    assert stats["service"]["requests_total"] == 1 and stats["service"]["requests_in_flight"] == 0


def test_concurrent_requests_add_to_corpus_without_loss_and_stats_reflect_load(tmp_path: Path) -> None:
    n = 12
    async def fn(_app, client):
        payloads = [{"what_you_like": f"It exports roadmap item {i} to a signed audit PDF for regulator number {i}.", "add_to_corpus": True} for i in range(n)]
        responses = await asyncio.gather(*(client.post("/score", json=payload) for payload in payloads))
        stats = (await client.get("/stats")).json()
        corpus = (await client.get("/corpus")).json()
        return responses, stats, corpus
    responses, stats, corpus = asyncio.run(with_app(app_settings(tmp_path, corpus_acceptance_threshold=0.1), FixtureLLM(delay=0.01), fn))
    assert all(response.status_code == 200 for response in responses)
    added = sum(response.json()["added_to_corpus"] for response in responses)
    assert added >= 1
    assert len(corpus) == added == len(CorpusStore(tmp_path / "corpus.json").list())
    assert stats["service"]["requests_total"] == n and stats["service"]["outcomes"] == {"ok": n}
    assert stats["service"]["latency_seconds"]["p95"] is not None
