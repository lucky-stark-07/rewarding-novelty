"""Input guardrails: local secret/PII detection and masking, plus LLM content moderation.

Masking runs before any model call, cache write, corpus write or log, so original values never
leave the process. Only placeholder types and counts are reported."""
from __future__ import annotations

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass, field
from .config import Settings
from .llm_client import LLM_UNAVAILABLE, LLMClient
from .prompts import MODERATE
from .schemas import FieldName, ModerationResponse, Submission
from .telemetry import span

# Ordered: earlier, more specific patterns claim text before later, broader ones.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SECRET", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("SECRET", re.compile(r"\b(?:sk-or-v1-[A-Za-z0-9]{16,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b")),
    ("SECRET", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("SECRET", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("SECRET", re.compile(r"(?i)\b(?:password|passwd|pwd|api[_-]?key|secret|access[_-]?token|auth[_-]?token)\s*[:=]\s*[\"']?[^\s\"',;]{6,}")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CREDIT_CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    ("IP_ADDRESS", re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")),
    # Must not start or end inside a longer digit-group run (e.g. an order number that failed the card check).
    ("PHONE", re.compile(r"(?<![\w.])(?<!\d[ -])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{2,4}[\s.-]\d{3,4}(?:[\s.-]\d{3,4})?(?![\w.])(?![ -]\d)")),
]


def _luhn(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, char in enumerate(digits):
        value = int(char)
        if i % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _accept(kind: str, match: str) -> bool:
    if kind == "CREDIT_CARD":
        digits = re.sub(r"\D", "", match)
        return 13 <= len(digits) <= 19 and _luhn(digits)
    if kind == "IP_ADDRESS":
        try:
            address = ipaddress.ip_address(match)
        except ValueError:
            return False
        return not address.is_unspecified
    if kind == "PHONE":
        return 9 <= len(re.sub(r"\D", "", match)) <= 15
    return True


@dataclass
class Masker:
    """Masks one request's text. Placeholders are numbered per type across all fields: [EMAIL_1], [SECRET_2]."""

    counts: Counter[str] = field(default_factory=Counter)
    _seen: dict[str, str] = field(default_factory=dict)

    def mask(self, text: str) -> str:
        for kind, pattern in _PATTERNS:
            text = pattern.sub(lambda match, kind=kind: self._replace(kind, match.group(0)), text)
        return text

    def _replace(self, kind: str, value: str) -> str:
        if value.startswith("[") and value.endswith("]") or not _accept(kind, value):
            return value
        if value not in self._seen:  # the same value masked twice gets the same placeholder
            self.counts[kind] += 1
            self._seen[value] = f"[{kind}_{self.counts[kind]}]"
        return self._seen[value]


def mask_submission(submission: Submission) -> tuple[Submission, Counter[str]]:
    masker = Masker()
    masked = submission.model_copy(update={field.value: masker.mask(submission.field_text(field)) for field in FieldName})
    return masked, masker.counts


# Deterministic floor for unambiguous directed abuse: blocks without an LLM call, so it is consistent
# and still works when the guard is down. Deliberately narrow; nuanced cases go to the LLM guard.
_DIRECTED_ABUSE = re.compile(
    r"(?i)\b(?:f+u+c+k+|f\*+c?k|fck|screw)\s*(?:you|u|off|yourself|this\s+(?:company|team|guy))\b"
    r"|\bstfu\b|\bgo\s+to\s+hell\b|\bgo\s+(?:kill|die)\b|\bkill\s+yourself\b|\bkys\b"
)


def local_block(masked: Submission) -> list[str]:
    text = " ".join(masked.field_text(field) for field in FieldName)
    return ["abuse"] if _DIRECTED_ABUSE.search(text) else []


async def moderate(masked: Submission, guard: LLMClient, settings: Settings) -> tuple[str, list[str], str]:
    """Return (verdict, categories, reason). verdict is allow|flag|block, or unavailable when the guard
    cannot answer (scoring continues, but the review must not be stored), or disabled."""
    if not settings.moderation_enabled:
        return "disabled", [], "Moderation is disabled by configuration."
    if categories := local_block(masked):
        with span("guard.moderation", source="local_rule", verdict="block"):
            return "block", categories, "The review contains abuse directed at a person or the reader."
    review = "\n".join(f"{field.value}: {masked.field_text(field).strip()}" for field in FieldName if masked.field_text(field).strip())
    with span("guard.moderation", model=settings.guard_model) as attrs:
        try:
            result = await guard.complete_json(MODERATE, model=settings.guard_model, variables={"review": review}, response_model=ModerationResponse)
        except LLM_UNAVAILABLE as exc:
            attrs["verdict"] = "unavailable"
            return "unavailable", [], f"Moderation guard unavailable ({type(exc).__name__}); the review will not be stored."
        attrs.update(verdict=result.verdict, categories=",".join(result.categories))
        return result.verdict, result.categories, result.reason


def warnings_for(counts: Counter[str]) -> list[str]:
    warnings = []
    if counts.get("SECRET"):
        warnings.append("Your review contained what looks like a password, API key or token. It was masked before scoring and not stored; rotate it if it is real.")
    personal = sorted(kind for kind in counts if kind != "SECRET")
    if personal:
        warnings.append(f"Personal data was masked before scoring and is never stored: {', '.join(k.lower().replace('_', ' ') for k in personal)}.")
    return warnings
