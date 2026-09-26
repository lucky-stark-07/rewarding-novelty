import asyncio
import re
import uuid
from .config import Settings
from .llm_client import LLM_UNAVAILABLE, LLMClient
from .prompts import EXTRACT_CLAIMS, FIELD_INTENTS
from .schemas import Claim, FieldClaimsResponse, FieldName, Submission
from .telemetry import current_trace, span

MAX_CLAIMS_PER_FIELD = 3
_SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    """Degraded-mode claim extraction: each sentence is a claim."""
    return [part.strip() for part in _SENTENCE_BREAK.split(text) if len(part.strip()) >= 3][:MAX_CLAIMS_PER_FIELD]


async def _extract_field(field: FieldName, text: str, llm: LLMClient, settings: Settings) -> list[Claim]:
    with span("extract", field=field.value) as attrs:
        try:
            data = await llm.complete_json(EXTRACT_CLAIMS, model=settings.fast_model, variables={"field": field.value, "field_intent": FIELD_INTENTS[field.value], "text": text}, response_model=FieldClaimsResponse)
            texts = [item.text.strip() for item in data.claims if item.text.strip()]
        except LLM_UNAVAILABLE as exc:
            reason = f"extract:{type(exc).__name__}"
            attrs.update(degraded=True, degraded_reason=reason)
            if (trace := current_trace.get()) is not None:
                trace.degrade(reason)
            texts = split_sentences(text)
        attrs["claims"] = len(texts)
    return [Claim(id=str(uuid.uuid4()), field=field, text=claim_text) for claim_text in texts]


async def extract_claims(submission: Submission, llm: LLMClient, settings: Settings) -> list[Claim]:
    """Extract atomic claims from each populated field concurrently; one fast-model call per field."""
    populated = [(field, submission.field_text(field).strip()) for field in FieldName if submission.field_text(field).strip()]
    per_field = await asyncio.gather(*(_extract_field(field, text, llm, settings) for field, text in populated))
    return [claim for claims in per_field for claim in claims]
