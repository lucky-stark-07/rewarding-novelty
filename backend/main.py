from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .config import Settings, get_settings
from .corpus import CorpusIndex, CorpusStore
from .embeddings import cache_snapshot, embed, run_embedder, warm_up
from .llm_client import LLMClient
from .prompts import EXTRACT_CLAIMS, GENERATE_CORPUS, JUDGE_COVERAGE, JUDGE_RELEVANCE
from .reference import REFERENCE_PRODUCT_DESCRIPTION
from .routes import corpus, submit
from .telemetry import ServiceStats, TraceSink


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    active = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await run_embedder(lambda _texts: warm_up(), [])
        app.state.settings = active
        app.state.llm = llm or LLMClient(active)
        app.state.index = await CorpusIndex.create(CorpusStore(active.corpus_path), embed, REFERENCE_PRODUCT_DESCRIPTION)
        app.state.stats = ServiceStats()
        app.state.trace_sink = TraceSink(active.trace_log_path)
        yield

    app = FastAPI(title="Rewarding Novelty API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[active.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["x-request-id"])
    app.include_router(submit.router)
    app.include_router(corpus.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats")
    async def stats(request: Request) -> dict:
        state = request.app.state
        return {
            **state.stats.snapshot(),
            "llm": state.llm.snapshot(),
            "embeddings_cache": cache_snapshot(),
            "corpus": {"entries": len(state.index.entries), "claims": state.index.claim_count},
            "config": {
                "fast_model": active.fast_model,
                "judge_model": active.judge_model,
                "low_threshold": active.low_threshold,
                "high_threshold": active.high_threshold,
                "entailment_top_k": active.entailment_top_k,
                "max_inflight_requests": active.max_inflight_requests,
                "prompt_versions": [prompt.PROMPT_VERSION for prompt in (EXTRACT_CLAIMS, JUDGE_RELEVANCE, JUDGE_COVERAGE, GENERATE_CORPUS)],
            },
        }

    return app


app = create_app()
