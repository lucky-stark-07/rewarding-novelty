import asyncio
import hmac
from fastapi import APIRouter, Header, HTTPException, Request
from ..data_gen import generate_corpus
from ..llm_client import LLM_UNAVAILABLE
from ..reference import REFERENCE_PRODUCT_DESCRIPTION
from ..schemas import CorpusEntry
router = APIRouter(tags=["corpus"])
_regenerating = asyncio.Lock()


@router.get("/corpus", response_model=list[CorpusEntry])
async def list_corpus(request: Request) -> list[CorpusEntry]:
    return request.app.state.index.entries


@router.post("/corpus/regenerate", response_model=list[CorpusEntry])
async def regenerate_corpus(request: Request, x_admin_token: str | None = Header(default=None)) -> list[CorpusEntry]:
    """Replace the whole comparison corpus with freshly generated synthetic reviews (paid, changes every future score)."""
    state = request.app.state
    configured = state.settings.admin_token
    if configured is None or not configured.get_secret_value():
        raise HTTPException(status_code=403, detail="Corpus regeneration is disabled on this server. Set ADMIN_TOKEN to enable it.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), configured.get_secret_value().encode()):
        raise HTTPException(status_code=401, detail="A valid admin token is required to regenerate the corpus.")
    if _regenerating.locked():
        raise HTTPException(status_code=409, detail="A corpus regeneration is already running.")
    async with _regenerating:
        try:
            entries = await generate_corpus(REFERENCE_PRODUCT_DESCRIPTION, state.llm)
        except (*LLM_UNAVAILABLE, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Corpus generation failed: {exc}") from exc
        await state.index.replace(entries)
    return entries
