"""Optional paid corpus generation; never runs on import or application startup."""
import asyncio
import uuid
from .config import get_settings
from .corpus import CorpusStore
from .llm_client import LLMClient
from .prompts import GENERATE_CORPUS
from .schemas import Claim, CorpusEntry, CorpusGenerationResponse, FieldName, Submission

async def generate_corpus(reference_text: str, client: LLMClient, n: int = 50) -> list[CorpusEntry]:
    """Generate entries without saving them; the caller decides where they are stored."""
    if not 1 <= n <= 50: raise ValueError("n must be between 1 and 50.")
    settings = get_settings()
    personas = ["product manager", "UX researcher", "engineering lead", "customer success manager", "startup founder", "enterprise portfolio director", "business analyst", "design operations lead", "growth marketer", "IT administrator"]
    companies = ["2-person startup", "20-person startup", "200-person scale-up", "global enterprise", "nonprofit", "regulated financial company", "health technology company", "consumer software company", "industrial manufacturer", "education organization"]
    sentiments = ["enthusiastic", "mostly positive with a concrete criticism", "mixed", "frustrated but fair", "neutral and specific"]
    variables = {"reference": reference_text, "n": n, "personas": ", ".join(personas), "companies": ", ".join(companies), "sentiments": ", ".join(sentiments)}
    try:
        data = await client.complete_json(GENERATE_CORPUS, model=settings.fast_model, variables=variables, response_model=CorpusGenerationResponse, temperature=0.9)
    except Exception:
        print(f"Corpus generation failed. {_usage(client)}")
        raise
    if len(data.reviews) != n: raise ValueError(f"Expected {n} generated reviews, got {len(data.reviews)}")
    entries = []
    for review in data.reviews:
        submission = Submission.model_validate(review.model_dump(exclude={"claims"}))
        entry_id = str(uuid.uuid4())
        if review.claims:
            claims = [Claim(id=str(uuid.uuid4()), field=claim.field, text=claim.text, source_submission_id=entry_id) for claim in review.claims]
        else:
            claims = [Claim(id=str(uuid.uuid4()), field=field, text=submission.field_text(field), source_submission_id=entry_id) for field in FieldName if submission.field_text(field).strip()]
        entries.append(CorpusEntry(id=entry_id, submission=submission, claims=claims))
    print(f"Corpus generation: {_usage(client)}")
    return entries

def _usage(client: LLMClient) -> str:
    metrics = client.metrics
    return f"{metrics['calls']:.0f} paid call(s), {metrics['memory_hits'] + metrics['disk_hits']:.0f} cache hit(s), {metrics['prompt_tokens']:.0f} prompt tokens, {metrics['completion_tokens']:.0f} completion tokens, ${metrics['cost_usd']:.4f}."

async def _main() -> None:
    from .reference import REFERENCE_PRODUCT_DESCRIPTION
    entries = await generate_corpus(REFERENCE_PRODUCT_DESCRIPTION, LLMClient(get_settings()))
    CorpusStore().replace(entries)
    print(f"Saved {len(entries)} corpus entries.")

if __name__ == "__main__":
    asyncio.run(_main())
