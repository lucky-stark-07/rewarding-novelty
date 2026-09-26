import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .config import Settings, get_settings
from .corpus import CorpusIndex, CorpusStore
from .embeddings import cache_snapshot, embed, warm_up
from .llm_client import LLMClient
from .routes import corpus, submit
from .telemetry import ServiceStats


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    active = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(warm_up)
        app.state.settings = active
        app.state.llm = llm or LLMClient(active)
        app.state.index = await CorpusIndex.create(CorpusStore(active.corpus_path), embed)
        app.state.stats = ServiceStats()
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
            "service": state.stats.snapshot(),
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
            },
        }

    return app


app = create_app()
