from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .routes import corpus, submit
app = FastAPI(title="Rewarding Novelty API")
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(submit.router)
app.include_router(corpus.router)
@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}
