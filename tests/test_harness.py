import asyncio
import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace
import httpx
import openai
import pytest
from pydantic import BaseModel
from tenacity import Future, RetryCallState
from backend import llm_client as llm_module
from backend.config import Settings
from backend.corpus import CorpusIndex, CorpusStore
from backend.embeddings import embed
from backend.llm_client import BudgetExceededError, CircuitBreaker, CircuitOpenError, LLMClient, UpstreamError, retry_after_seconds
from backend.main import create_app
from backend.prompts import EXTRACT_CLAIMS, JUDGE_COVERAGE, JUDGE_RELEVANCE, Prompt, load_prompt
from backend.schemas import Claim, CorpusEntry, FieldName, Submission
from tests.conftest import FIXTURES, FixtureLLM, run_score

REQUEST = httpx.Request("POST", "https://openrouter.test/api/v1/chat/completions")
TEST_PROMPT = Prompt(name="test", version="1", system="Return JSON.", user=EXTRACT_CLAIMS.user.__class__("$text"))


class Answer(BaseModel):
    value: int


def status_error(status: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    response = httpx.Response(status, headers=headers or {}, request=REQUEST)
    return openai.APIStatusError(f"HTTP {status}", response=response, body=None)


class FakeCompletions:
    """Stands in for AsyncOpenAI.chat.completions. `script` is consumed per call: an exception
    is raised, a string is returned as content; afterwards it returns {"value": 1}."""

    def __init__(self, script: list | None = None, delay: float = 0.01, cost: float | None = 0.001, served_model: str = "served/model", cached_tokens: int = 4) -> None:
        self.script = list(script or [])
        self.delay = delay
        self.cost = cost
        self.served_model = served_model
        self.cached_tokens = cached_tokens
        self.calls: list[dict] = []
        self.active = self.peak = 0

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            step = self.script.pop(0) if self.script else json.dumps({"value": 1})
            if isinstance(step, BaseException):
                raise step
            usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=SimpleNamespace(cached_tokens=self.cached_tokens))
            if self.cost is not None:
                usage.cost = self.cost
            return SimpleNamespace(model=self.served_model, usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=step))])
        finally:
            self.active -= 1


def make_client(tmp_path: Path, fake: FakeCompletions, **overrides) -> LLMClient:
    client = LLMClient(Settings(cache_dir=tmp_path / "cache", openrouter_api_key="test-key", **overrides))
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))  # type: ignore[assignment]
    return client


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "RETRY_BASE_SECONDS", 0.0)


def ask(client: LLMClient, text: str, prompt: Prompt = TEST_PROMPT, **kwargs):
    return client.complete_json(prompt, model=kwargs.pop("model", "m"), variables={"text": text}, response_model=Answer, **kwargs)


# ---- prompts -------------------------------------------------------------------------------

def test_prompts_load_from_markdown_with_versions_and_user_text_last() -> None:
    for prompt in (EXTRACT_CLAIMS, JUDGE_RELEVANCE, JUDGE_COVERAGE):
        assert prompt.PROMPT_VERSION.startswith(prompt.name + "@")
        assert prompt.system and "$" not in prompt.system
    rendered = JUDGE_RELEVANCE.render(reference="REF", field="what_you_like", field_intent="INTENT", claims="USER_CLAIMS")
    assert rendered.index("REF") < rendered.index("INTENT") < rendered.index("USER_CLAIMS")
    assert EXTRACT_CLAIMS.render(field="f", field_intent="i", text="USER TEXT").rstrip().endswith("USER TEXT")
    assert load_prompt("judge_coverage").version == JUDGE_COVERAGE.version


# ---- async client: concurrency, caching -----------------------------------------------------

def test_llm_concurrency_is_bounded_by_semaphore(tmp_path: Path) -> None:
    fake = FakeCompletions(delay=0.02)
    async def run():
        client = make_client(tmp_path, fake, llm_max_concurrency=3)
        await asyncio.gather(*(ask(client, f"prompt {i}") for i in range(20)))
    asyncio.run(run())
    assert len(fake.calls) == 20 and fake.peak <= 3


def test_identical_concurrent_prompts_share_one_call_then_hit_memory_lru(tmp_path: Path) -> None:
    fake = FakeCompletions(delay=0.02)
    async def run():
        client = make_client(tmp_path, fake)
        results = await asyncio.gather(*(ask(client, "same") for _ in range(10)))
        await ask(client, "same")
        return client, results
    client, results = asyncio.run(run())
    assert len(fake.calls) == 1 and all(result.value == 1 for result in results)
    assert client.metrics["inflight_dedup"] == 9 and client.metrics["memory_hits"] == 1 and client.metrics["disk_hits"] == 0


def test_disk_cache_serves_a_fresh_process(tmp_path: Path) -> None:
    fake = FakeCompletions()
    asyncio.run(ask(make_client(tmp_path, fake), "persist me"))
    fresh = make_client(tmp_path, fake)
    asyncio.run(ask(fresh, "persist me"))
    assert len(fake.calls) == 1 and fresh.metrics["disk_hits"] == 1


def test_cache_key_covers_model_prompt_version_temperature_and_schema() -> None:
    class Other(BaseModel):
        other: str
    messages = [{"role": "user", "content": "x"}]
    base = LLMClient.cache_key("m", "p@1", 0, Answer, messages)
    assert base == LLMClient.cache_key("m", "p@1", 0, Answer, messages)
    variants = [LLMClient.cache_key("m2", "p@1", 0, Answer, messages), LLMClient.cache_key("m", "p@2", 0, Answer, messages), LLMClient.cache_key("m", "p@1", 0.5, Answer, messages), LLMClient.cache_key("m", "p@1", 0, Other, messages), LLMClient.cache_key("m", "p@1", 0, Answer, [{"role": "user", "content": "y"}])]
    assert len({base, *variants}) == 6


def test_cache_disabled_flag_bypasses_cache_and_dedup(tmp_path: Path) -> None:
    fake = FakeCompletions(delay=0.01)
    async def run():
        client = make_client(tmp_path, fake, cache_enabled=False)
        await asyncio.gather(*(ask(client, "same") for _ in range(4)))
        await ask(client, "same")
        return client
    client = asyncio.run(run())
    assert len(fake.calls) == 5
    assert not list((tmp_path / "cache").glob("*.json"))
    assert client.snapshot()["cache_hit_rate"] == 0.0


# ---- reliability ----------------------------------------------------------------------------

def test_schema_failure_triggers_one_repair_with_the_error(tmp_path: Path) -> None:
    fake = FakeCompletions(script=[json.dumps({"value": "not a number"}), json.dumps({"value": 1})])
    result = asyncio.run(ask(make_client(tmp_path, fake), "repair me"))
    assert result.value == 1 and len(fake.calls) == 2
    assert "failed validation" in fake.calls[1]["messages"][1]["content"]


def test_second_invalid_output_raises_upstream_error(tmp_path: Path) -> None:
    fake = FakeCompletions(script=["not json", "still not json"])
    with pytest.raises(UpstreamError):
        asyncio.run(ask(make_client(tmp_path, fake), "hopeless"))
    assert len(fake.calls) == 2


def test_retries_429_and_5xx_and_timeouts_then_succeeds(tmp_path: Path) -> None:
    fake = FakeCompletions(script=[status_error(429, {"retry-after": "0"}), openai.APITimeoutError(request=REQUEST), json.dumps({"value": 1})])
    client = make_client(tmp_path, fake)
    assert asyncio.run(ask(client, "flaky")).value == 1
    assert len(fake.calls) == 3 and client.metrics["retries"] == 2


def test_gives_up_after_three_attempts(tmp_path: Path) -> None:
    fake = FakeCompletions(script=[status_error(503)] * 5)
    with pytest.raises(UpstreamError):
        asyncio.run(ask(make_client(tmp_path, fake), "down"))
    assert len(fake.calls) == 3


def test_client_errors_are_not_retried(tmp_path: Path) -> None:
    fake = FakeCompletions(script=[status_error(400)])
    with pytest.raises(UpstreamError):
        asyncio.run(ask(make_client(tmp_path, fake), "bad request"))
    assert len(fake.calls) == 1


def test_retry_after_is_honoured(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeCompletions(), llm_max_retry_after_seconds=20)
    state = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
    outcome = Future(attempt_number=1)
    outcome.set_exception(status_error(429, {"retry-after": "7"}))
    state.outcome = outcome
    assert client._wait(state) == 7
    assert retry_after_seconds(status_error(429, {"retry-after-ms": "1500"})) == 1.5
    assert retry_after_seconds(status_error(429, {"retry-after": "999"})) == 999
    outcome = Future(attempt_number=1)
    outcome.set_exception(status_error(429, {"retry-after": "999"}))
    state.outcome = outcome
    assert client._wait(state) == 20


def test_openrouter_fallbacks_usage_and_served_model_are_recorded(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.llm_client")
    fake = FakeCompletions(cost=0.0042, served_model="backup/model", cached_tokens=6)
    client = make_client(tmp_path, fake, judge_model="primary/model", judge_model_fallbacks="backup/model, other/model")
    asyncio.run(ask(client, "fallback", model="primary/model"))
    extra = fake.calls[0]["extra_body"]
    assert extra["models"] == ["primary/model", "backup/model", "other/model"] and extra["usage"] == {"include": True}
    assert client.metrics["cost_usd"] == pytest.approx(0.0042) and client.metrics["cached_tokens"] == 6
    assert client.served_models == {"backup/model": 1}
    assert any("served_model=backup/model" in record.getMessage() for record in caplog.records)


def test_cost_is_estimated_when_not_reported(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeCompletions(cost=None), fast_model="m")
    asyncio.run(ask(client, "estimate"))
    assert client.metrics["cost_usd"] == pytest.approx(10 * 0.10 / 1e6 + 5 * 0.40 / 1e6)


def test_circuit_opens_after_three_consecutive_failures(tmp_path: Path) -> None:
    fake = FakeCompletions(script=[status_error(400)] * 3)
    async def run():
        client = make_client(tmp_path, fake)
        for i in range(3):
            with pytest.raises(UpstreamError):
                await ask(client, f"p{i}")
        with pytest.raises(CircuitOpenError):
            await ask(client, "p-open")
        return client
    client = asyncio.run(run())
    assert len(fake.calls) == 3 and client.breaker.state == "open"


def test_budget_cap_stops_upstream_calls(tmp_path: Path) -> None:
    fake = FakeCompletions(cost=0.3)
    async def run():
        client = make_client(tmp_path, fake, llm_budget_usd=0.5)
        await ask(client, "a")
        await ask(client, "b")
        with pytest.raises(BudgetExceededError):
            await ask(client, "c")
        await ask(client, "a")  # cached answers stay available
    asyncio.run(run())
    assert len(fake.calls) == 2


def test_circuit_breaker_half_open_probe_closes_on_success() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10, clock=lambda: now[0])
    breaker.on_failure()
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
    now[0] = 11
    breaker.before_call()
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
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


def test_settings_never_expose_api_key() -> None:
    settings = Settings(openrouter_api_key="sk-or-secret-value")
    assert "sk-or-secret-value" not in repr(settings) and "sk-or-secret-value" not in str(settings.model_dump())


# ---- degraded scoring -----------------------------------------------------------------------

class DownLLM:
    async def complete_json(self, *_args, **_kwargs):
        raise CircuitOpenError(30)

    def snapshot(self) -> dict:
        return {"circuit_breaker": {"state": "open"}}


def test_llm_outage_degrades_to_embedding_only_scoring(corpus: CorpusStore) -> None:
    result = run_score(Submission.model_validate(FIXTURES["novel_relevant"]), corpus, llm=DownLLM(), add_to_corpus=True, settings=Settings(corpus_acceptance_threshold=0.0))
    assert result.degraded and "CircuitOpenError" in (result.degraded_reason or "")
    assert result.meta["degraded"] is True and result.meta["llm_calls"] == 0
    assert result.added_to_corpus is False and len(corpus.list()) == 1
    claims = [claim for field in result.field_scores for claim in field.claims]
    assert claims and all(not claim.entailment_judged for claim in claims)
    assert all(claim.relevance_reason.startswith("Degraded") for claim in claims)


def test_degraded_mode_still_rejects_off_topic_and_gibberish(corpus: CorpusStore) -> None:
    for case in ("irrelevant", "gibberish"):
        assert run_score(Submission.model_validate(FIXTURES[case]), corpus, llm=DownLLM()).submission_score <= 0.34


# ---- corpus ---------------------------------------------------------------------------------

def _entry(i: int) -> CorpusEntry:
    return CorpusEntry(id=f"e{i}", submission=Submission(what_you_like=f"Distinct observation number {i}."), claims=[Claim(id=f"c{i}", field=FieldName.WHAT_YOU_LIKE, text=f"Distinct observation number {i}.")])


def test_concurrent_corpus_appends_do_not_lose_entries(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    threads = [threading.Thread(target=CorpusStore(path).append, args=(_entry(i),)) for i in range(25)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(entry.id for entry in CorpusStore(path).list()) == sorted(f"e{i}" for i in range(25))


def test_corpus_index_single_matrix_search_is_field_scoped(tmp_path: Path) -> None:
    async def run():
        index = await CorpusIndex.create(CorpusStore(tmp_path / "corpus.json"), embed)
        await index.add(_entry(1))
        await index.add(_entry(1))
        other = CorpusEntry(id="d", submission=Submission(what_you_dislike="Distinct observation number 1."), claims=[Claim(id="d1", field=FieldName.WHAT_YOU_DISLIKE, text="Distinct observation number 1.")])
        await index.add(other)
        vectors = await index.embed(["Distinct observation number 1."])
        return index, index.search(vectors, [FieldName.WHAT_YOU_LIKE], 5)[0]
    index, neighbors = asyncio.run(run())
    assert index.matrix is not None and index.matrix.shape[0] == 2 and len(index.entries) == 2
    assert [claim.id for claim, _ in neighbors] == ["c1"] and neighbors[0][1] == pytest.approx(1.0, abs=1e-4)
    assert index.find_duplicate(Submission(what_you_like="  distinct OBSERVATION number 1. ")) is not None


# ---- API ------------------------------------------------------------------------------------

def app_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(corpus_path=tmp_path / "corpus.json", cache_dir=tmp_path / "cache", trace_log_path=tmp_path / "logs" / "traces.jsonl", **overrides)


async def with_app(settings: Settings, llm, fn):
    app = create_app(settings, llm=llm)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await fn(app, client)


def test_score_response_meta_trace_log_and_stats(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="noveltylens.requests")
    async def fn(_app, client):
        response = await client.post("/score", headers={"x-request-id": "trace-123"}, json={"what_you_like": "Useful", "what_you_dislike": "Slow", "problem_solved": "Planning"})
        return response, (await client.get("/stats")).json()
    settings = app_settings(tmp_path)
    response, stats = asyncio.run(with_app(settings, FixtureLLM(), fn))
    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["trace_id"] == "trace-123" == response.headers["x-request-id"]
    assert {"extract", "embed", "search", "relevance", "aggregate"} <= {span["name"] for span in meta["spans"]}
    lines = [json.loads(line) for line in settings.trace_log_path.read_text().splitlines()]
    assert len(lines) == len(meta["spans"]) and all(line["trace_id"] == "trace-123" for line in lines)
    logged = json.loads(next(record for record in caplog.records if record.name == "noveltylens.requests").message)
    assert logged["trace_id"] == "trace-123" and "spans" not in logged
    assert stats["request_count"] == 1 and stats["latency_ms"]["p50"] is not None and stats["latency_ms"]["p95"] is not None
    assert {"total_cost_usd", "cache_hit_rate", "degraded_count"} <= set(stats)


def test_score_route_rejects_overlong_field(tmp_path: Path) -> None:
    async def fn(_app, client):
        return await client.post("/score", json={"what_you_like": "x" * 4001})
    assert asyncio.run(with_app(app_settings(tmp_path), FixtureLLM(), fn)).status_code == 422


def test_overload_is_shed_with_503(tmp_path: Path) -> None:
    async def fn(app, client):
        app.state.stats.in_flight = app.state.settings.max_inflight_requests
        response = await client.post("/score", json={"what_you_like": "Useful"})
        app.state.stats.in_flight = 0
        return response, (await client.get("/stats")).json()
    response, stats = asyncio.run(with_app(app_settings(tmp_path, max_inflight_requests=2), FixtureLLM(), fn))
    assert response.status_code == 503 and response.headers["retry-after"] == "1"
    assert stats["rejected_overload"] == 1


def test_llm_outage_returns_degraded_200_and_is_counted(tmp_path: Path) -> None:
    async def fn(_app, client):
        response = await client.post("/score", json={"what_you_like": "It links customer feedback to roadmap items."})
        return response, (await client.get("/stats")).json()
    response, stats = asyncio.run(with_app(app_settings(tmp_path), DownLLM(), fn))
    body = response.json()
    assert response.status_code == 200 and body["degraded"] is True and body["meta"]["degraded"] is True and body["degraded_reason"]
    assert stats["degraded_count"] == 1 and stats["outcomes"] == {"degraded": 1}


def test_corpus_regeneration_is_disabled_without_admin_token(tmp_path: Path, monkeypatch) -> None:
    from backend.routes import corpus as corpus_route
    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("generation must not start")
    monkeypatch.setattr(corpus_route, "generate_corpus", must_not_run)
    async def fn(_app, client):
        return await client.post("/corpus/regenerate", headers={"x-admin-token": "anything"}), (await client.get("/stats")).json()
    response, stats = asyncio.run(with_app(app_settings(tmp_path), FixtureLLM(), fn))
    assert response.status_code == 403 and stats["config"]["corpus_regenerate_enabled"] is False


def test_corpus_regeneration_requires_the_right_token_and_runs_once(tmp_path: Path, monkeypatch) -> None:
    from backend.routes import corpus as corpus_route
    release = asyncio.Event()
    calls = []
    async def fake_generate(*_args, **_kwargs):
        calls.append(1)
        await release.wait()
        return [_entry(1), _entry(2)]
    monkeypatch.setattr(corpus_route, "generate_corpus", fake_generate)
    async def fn(_app, client):
        missing = await client.post("/corpus/regenerate")
        wrong = await client.post("/corpus/regenerate", headers={"x-admin-token": "wrong"})
        first = asyncio.create_task(client.post("/corpus/regenerate", headers={"x-admin-token": "s3cret"}))
        while not calls:
            await asyncio.sleep(0.01)
        second = await client.post("/corpus/regenerate", headers={"x-admin-token": "s3cret"})
        release.set()
        return missing, wrong, await first, second, (await client.get("/corpus")).json()
    missing, wrong, first, second, corpus = asyncio.run(with_app(app_settings(tmp_path, admin_token="s3cret"), FixtureLLM(), fn))
    assert missing.status_code == 401 and wrong.status_code == 401
    assert second.status_code == 409 and first.status_code == 200
    assert [entry["id"] for entry in corpus] == ["e1", "e2"] and len(calls) == 1


def test_concurrent_requests_add_to_corpus_without_loss(tmp_path: Path) -> None:
    n = 12
    async def fn(_app, client):
        payloads = [{"what_you_like": f"It exports roadmap item {i} to a signed audit PDF for regulator number {i}.", "add_to_corpus": True} for i in range(n)]
        responses = await asyncio.gather(*(client.post("/score", json=payload) for payload in payloads))
        return responses, (await client.get("/stats")).json(), (await client.get("/corpus")).json()
    responses, stats, corpus = asyncio.run(with_app(app_settings(tmp_path, corpus_acceptance_threshold=0.1), FixtureLLM(delay=0.01), fn))
    assert all(response.status_code == 200 for response in responses)
    added = sum(response.json()["added_to_corpus"] for response in responses)
    assert added >= 1 and len(corpus) == added == len(CorpusStore(tmp_path / "corpus.json").list())
    assert stats["request_count"] == n and stats["outcomes"] == {"ok": n}
