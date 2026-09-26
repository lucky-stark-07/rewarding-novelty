import asyncio
import json
import logging
from pathlib import Path
import pytest
from backend.config import Settings
from backend.corpus import CorpusStore
from backend.guardrails import Masker, mask_submission
from backend.llm_client import CircuitOpenError
from backend.schemas import Submission
from tests.conftest import FixtureLLM, run_score
from tests.test_harness import app_settings, with_app

SECRETS = {
    "openrouter": "sk-or-v1-0123456789abcdef0123456789abcdef",
    "openai": "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz012345",
    "aws": "AKIAIOSFODNN7EXAMPLE",
    "github": "ghp_0123456789abcdefghijklmnopqrstuvwxyzAB",
    "slack": "xoxb-1234567890-abcdefghijkl",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
}
PII = {
    "EMAIL": "priya.sharma@acme-corp.com",
    "PHONE": "+1 (415) 555-0132",
    "CREDIT_CARD": "4111 1111 1111 1111",
    "IP_ADDRESS": "192.168.10.42",
}
# Must survive untouched: ordinary review language that looks number- or key-like.
FALSE_POSITIVES = [
    "The API rate limit is too low for our sync.",
    "Version v2.4.1 fixed the export bug.",
    "It costs $1,200 per year for 25 seats.",
    "We use sk-learn and Jira alongside it.",
    "Loading takes 3.5 seconds on a 100 Mbps link.",
    "Our 2024-2025 roadmap has 12 initiatives.",
    "Password reset emails arrive quickly.",
    "Order number 1234 5678 9012 3456 was wrong.",  # 16 digits but fails the Luhn check
]


@pytest.mark.parametrize("name, value", SECRETS.items())
def test_secrets_are_masked(name: str, value: str) -> None:
    masker = Masker()
    masked = masker.mask(f"Our key {value} leaked into the review.")
    assert value not in masked and "[SECRET_1]" in masked and masker.counts == {"SECRET": 1}


def test_secret_assignments_and_private_keys_are_masked() -> None:
    masker = Masker()
    text = "Config was api_key = 'hunter2hunter2' and password: Tr0ub4dor&3 then -----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
    masked = masker.mask(text)
    assert "hunter2hunter2" not in masked and "Tr0ub4dor" not in masked and "MIIEow" not in masked
    assert masker.counts["SECRET"] == 3


@pytest.mark.parametrize("kind, value", PII.items())
def test_pii_is_masked(kind: str, value: str) -> None:
    masker = Masker()
    masked = masker.mask(f"Contact {value} for details.")
    assert value not in masked and f"[{kind}_1]" in masked


@pytest.mark.parametrize("text", FALSE_POSITIVES)
def test_ordinary_review_text_is_not_masked(text: str) -> None:
    masker = Masker()
    assert masker.mask(text) == text and not masker.counts


def test_same_value_gets_same_placeholder_across_fields() -> None:
    email = PII["EMAIL"]
    masked, counts = mask_submission(Submission(what_you_like=f"Support at {email} is fast.", what_you_dislike=f"But {email} never escalates.", problem_solved="Planning."))
    assert "[EMAIL_1]" in masked.what_you_like and "[EMAIL_1]" in masked.what_you_dislike and counts == {"EMAIL": 1}


# ---- pipeline: originals never leave the process -------------------------------------------

def _leaky_submission() -> Submission:
    return Submission(
        what_you_like=f"Roadmap items link to feedback; email {PII['EMAIL']} for access.",
        what_you_dislike=f"We pasted {SECRETS['openrouter']} into a note and it was visible to everyone.",
        problem_solved=f"Support called {PII['PHONE']} less often after launch.",
    )


def _originals() -> list[str]:
    return [PII["EMAIL"], SECRETS["openrouter"], PII["PHONE"]]


def test_llm_calls_and_stored_corpus_only_see_masked_text(tmp_path: Path) -> None:
    llm = FixtureLLM()
    store = CorpusStore(tmp_path / "corpus.json")
    result = run_score(_leaky_submission(), store, llm=llm, settings=Settings(corpus_acceptance_threshold=0.0), add_to_corpus=True)
    sent = json.dumps([variables for _, variables in llm.calls])
    stored = (tmp_path / "corpus.json").read_text()
    response = result.model_dump_json()
    for original in _originals():
        assert original not in sent and original not in stored and original not in response
    assert "[EMAIL_1]" in stored and "[SECRET_1]" in sent
    assert result.added_to_corpus is True
    assert result.guardrails["masked"] == {"EMAIL": 1, "SECRET": 1, "PHONE": 1} and result.guardrails["moderation"] == "allow"
    assert any("rotate" in warning for warning in result.guardrails["warnings"])


def test_logs_traces_and_stats_never_contain_original_values(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    settings = app_settings(tmp_path)
    async def fn(_app, client):
        response = await client.post("/score", json=_leaky_submission().model_dump())
        return response, (await client.get("/stats")).json()
    response, stats = asyncio.run(with_app(settings, FixtureLLM(), fn))
    assert response.status_code == 200
    everything = response.text + settings.trace_log_path.read_text() + "\n".join(record.getMessage() for record in caplog.records) + json.dumps(stats)
    for original in _originals():
        assert original not in everything
    assert stats["guardrails"]["masked_by_type"] == {"EMAIL": 1, "SECRET": 1, "PHONE": 1}


# ---- moderation -----------------------------------------------------------------------------

def test_blocked_review_scores_zero_and_is_never_stored(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus.json")
    result = run_score(Submission(what_you_like="BLOCK-MARKER Roadmaps are clear."), store, settings=Settings(corpus_acceptance_threshold=0.0), add_to_corpus=True)
    assert result.submission_score == 0.0 and result.reason == "content_policy"
    assert result.guardrails["moderation"] == "block" and result.guardrails["categories"] == ["threat"]
    assert result.added_to_corpus is False and store.list() == []


def test_flagged_review_is_scored_but_not_stored(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus.json")
    result = run_score(Submission(what_you_like="FLAG-MARKER Roadmap items link straight to customer feedback."), store, settings=Settings(corpus_acceptance_threshold=0.0), add_to_corpus=True)
    assert result.submission_score > 0 and result.guardrails["moderation"] == "flag"
    assert result.added_to_corpus is False and store.list() == []


@pytest.mark.parametrize("text", ["fuck off", "Fuck you and your roadmap", "stfu", "go to hell", "F*ck off, this tool is useless"])
def test_directed_abuse_is_blocked_locally_without_a_guard_call(tmp_path: Path, text: str) -> None:
    from backend.corpus import CorpusIndex
    from backend.embeddings import embed
    from backend.novelty import score_submission
    async def run():
        index = await CorpusIndex.create(CorpusStore(tmp_path / "corpus.json"), embed)
        # GuardDown would fail the request's moderation if it were called; a local block must not need it.
        return await score_submission(Submission(what_you_like=text), index, FixtureLLM(), settings=Settings(), guard=GuardDown())
    result = asyncio.run(run())
    assert result.guardrails["moderation"] == "block" and result.guardrails["categories"] == ["abuse"]
    assert result.submission_score == 0.0 and result.reason == "content_policy"


@pytest.mark.parametrize("text", ["The damn export breaks every time.", "The reporting is garbage.", "Scunthorpe office uses the roadmap daily.", "We had to fuck around with CSV exports for hours."])
def test_local_abuse_rule_leaves_feedback_to_the_llm_guard(text: str) -> None:
    from backend.guardrails import local_block
    assert local_block(Submission(what_you_dislike=text)) == []


class GuardDown:
    async def complete_json(self, *_args, **_kwargs):
        raise CircuitOpenError(30)


def test_guard_outage_scores_but_fails_closed_for_storage(tmp_path: Path) -> None:
    from backend.corpus import CorpusIndex
    from backend.embeddings import embed
    from backend.novelty import score_submission
    store = CorpusStore(tmp_path / "corpus.json")
    async def run():
        index = await CorpusIndex.create(store, embed)
        return await score_submission(Submission(what_you_like="Roadmap items link straight to customer feedback."), index, FixtureLLM(), settings=Settings(corpus_acceptance_threshold=0.0), add_to_corpus=True, guard=GuardDown())
    result = asyncio.run(run())
    assert result.submission_score > 0 and result.guardrails["moderation"] == "unavailable"
    assert result.added_to_corpus is False and store.list() == []


def test_guard_settings_point_at_a_separate_endpoint() -> None:
    settings = Settings(openrouter_api_key="main-key", guard_base_url="http://llm.internal:8000/v1", guard_api_key="onprem-key", guard_model="llama-3.1-8b-instruct")
    guard = settings.guard_settings()
    assert guard.openrouter_base_url == "http://llm.internal:8000/v1" and guard.fast_model == "llama-3.1-8b-instruct"
    assert guard.openrouter_api_key.get_secret_value() == "onprem-key"
    assert Settings(openrouter_api_key="main-key").guard_settings().openrouter_base_url == "https://openrouter.ai/api/v1"
