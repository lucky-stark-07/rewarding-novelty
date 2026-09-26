from fastapi import APIRouter, HTTPException, Request
from ..data_gen import generate_corpus
from ..llm_client import CircuitOpenError, UpstreamError
from ..reference import REFERENCE_PRODUCT_DESCRIPTION
from ..schemas import CorpusEntry
router = APIRouter(tags=["corpus"])


@router.get("/corpus", response_model=list[CorpusEntry])
async def list_corpus(request: Request) -> list[CorpusEntry]:
    return request.app.state.index.entries


@router.post("/corpus/regenerate", response_model=list[CorpusEntry])
async def regenerate_corpus(request: Request) -> list[CorpusEntry]:
    state = request.app.state
    try:
        entries = await generate_corpus(REFERENCE_PRODUCT_DESCRIPTION, state.llm)
    except (CircuitOpenError, UpstreamError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Corpus generation failed: {exc}") from exc
    await state.index.replace(entries)
    return entries
