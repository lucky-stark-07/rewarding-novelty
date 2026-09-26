"""Optional paid corpus generation; never runs on import or application startup."""
import asyncio
import uuid
from .config import get_settings
from .corpus import CorpusStore
from .llm_client import LLMClient
from .schemas import Claim, CorpusEntry, CorpusGenerationResponse, FieldName, Submission

async def generate_corpus(reference_text: str, client: LLMClient, n: int = 50) -> list[CorpusEntry]:
    """Generate entries without saving them; the caller decides where they are stored."""
    if not 1 <= n <= 50: raise ValueError("n must be between 1 and 50.")
    settings = get_settings()
    personas = ["product manager", "UX researcher", "engineering lead", "customer success manager", "startup founder", "enterprise portfolio director", "business analyst", "design operations lead", "growth marketer", "IT administrator"]
    companies = ["2-person startup", "20-person startup", "200-person scale-up", "global enterprise", "nonprofit", "regulated financial company", "health technology company", "consumer software company", "industrial manufacturer", "education organization"]
    sentiments = ["enthusiastic", "mostly positive with a concrete criticism", "mixed", "frustrated but fair", "neutral and specific"]
    prompt = (
        f"Reference product:\n{reference_text}\n\nGenerate exactly {n} distinct G2-style reviews. "
        f"Mix personas ({', '.join(personas)}), company sizes and industries ({', '.join(companies)}, among others), "
        f"sentiments ({', '.join(sentiments)}), and experience levels (new user, daily user, admin, executive buyer). "
        "Avoid repeating the same benefits, complaints, wording, or workflows. Each review has the three required fields "
        "what_you_like, what_you_dislike, problem_solved, plus a claims array. Each claim has field and concise text and "
        "must faithfully express one atomic statement from its field. Use all three fields per review."
    )
    try:
        data = await client.complete_json(model=settings.fast_model, system="Generate varied realistic product reviews. Return a top-level JSON object with one key named reviews, whose value is an array. Return valid JSON only.", prompt=prompt, response_model=CorpusGenerationResponse, temperature=0.9, span_name="llm.generate_corpus")
    except Exception:
        print(f"Corpus generation failed after {client.metrics['calls']} paid call(s), {client.metrics['cache_hits']} cache hit(s), {client.metrics['prompt_tokens']} prompt tokens, {client.metrics['completion_tokens']} completion tokens, estimated ${client.metrics['estimated_cost_usd']:.4f}.")
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
    print(f"Corpus generation: {client.metrics['calls']} paid call(s), {client.metrics['cache_hits']} cache hit(s), {client.metrics['prompt_tokens']} prompt tokens, {client.metrics['completion_tokens']} completion tokens, estimated ${client.metrics['estimated_cost_usd']:.4f}.")
    return entries

async def _main() -> None:
    from .reference import REFERENCE_PRODUCT_DESCRIPTION
    entries = await generate_corpus(REFERENCE_PRODUCT_DESCRIPTION, LLMClient(get_settings()))
    CorpusStore().replace(entries)
    print(f"Saved {len(entries)} corpus entries.")

if __name__ == "__main__":
    asyncio.run(_main())
