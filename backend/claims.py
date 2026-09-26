import uuid
from .config import get_settings
from .llm_client import LLMClient
from .schemas import Claim, ClaimExtractionResponse, FieldName, Submission


async def extract_claims(submission: Submission, llm: LLMClient) -> list[Claim]:
    """Extract concise, independently checkable claims from the three review fields."""
    settings = get_settings()
    field_values = {field.value: submission.field_text(field).strip() for field in FieldName if submission.field_text(field).strip()}
    if not field_values:
        return []

    def only_populated_fields(data: ClaimExtractionResponse) -> None:
        stray = {item.field.value for item in data.claims} - set(field_values)
        if stray:
            raise ValueError(f"claims were returned for empty fields: {sorted(stray)}")

    data = await llm.complete_json(
        model=settings.fast_model,
        system=(
            "You extract atomic claims from product reviews. Return JSON only as "
            "{\"claims\":[{\"field\":\"what_you_like|what_you_dislike|problem_solved\",\"text\":\"...\"}]}. "
            "Each claim must be a concise factual proposition grounded only in the input. "
            "Keep each distinct detail as its own claim instead of merging it into a broader one. "
            "Do not invent details. Only use a field that has nonempty input. Return at most three claims per field."
        ),
        prompt=f"Review fields:\n{field_values}",
        response_model=ClaimExtractionResponse,
        check=only_populated_fields,
        span_name="llm.extract_claims",
    )
    return [Claim(id=str(uuid.uuid4()), field=item.field, text=item.text.strip()) for item in data.claims if item.text.strip()]
