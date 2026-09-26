import uuid
from .config import get_settings
from .llm_client import LLMClient
from .schemas import Claim, ClaimExtractionResponse, FieldName, Submission

def extract_claims(submission: Submission, llm: LLMClient | None = None) -> list[Claim]:
    """Extract concise, independently checkable claims from the three review fields."""
    settings = get_settings()
    field_values = {field.value: submission.field_text(field).strip() for field in FieldName if submission.field_text(field).strip()}
    if not field_values:
        return []
    client = llm or LLMClient(settings)
    data = client.complete_json(
        model=settings.fast_model,
        system=(
            "You extract atomic claims from product reviews. Return JSON only as "
            "{\"claims\":[{\"field\":\"what_you_like|what_you_dislike|problem_solved\",\"text\":\"...\"}]}. "
            "Each claim must be a concise factual proposition grounded only in the input. "
            "Do not invent details. Only use a field that has nonempty input. Return at most three claims per field."
        ),
        prompt=f"Review fields:\n{field_values}",
        response_model=ClaimExtractionResponse,
    )
    claims: list[Claim] = []
    for item in data.claims:
        field = item.field
        text = item.text.strip()
        if text:
            claims.append(Claim(id=str(uuid.uuid4()), field=field, text=text))
    return claims
