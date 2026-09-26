from fastapi import APIRouter, HTTPException
from ..corpus import CorpusStore
from ..data_gen import generate_corpus
from ..reference import REFERENCE_PRODUCT_DESCRIPTION
from ..schemas import CorpusEntry
router = APIRouter(tags=["corpus"])

@router.get("/corpus", response_model=list[CorpusEntry])
def list_corpus() -> list[CorpusEntry]: return CorpusStore().list()

@router.post("/corpus/regenerate", response_model=list[CorpusEntry])
def regenerate_corpus() -> list[CorpusEntry]:
    try: return generate_corpus(REFERENCE_PRODUCT_DESCRIPTION)
    except (RuntimeError, ValueError) as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
