"""Agent prompts live as Markdown files beside this module; this loader turns them into typed constants.

File format: YAML-like front matter with `name` and `version`, then `# <Section>` headings.
Prompt files have `# System` (static instructions) and `# User` (a `string.Template` whose
variable, user-supplied text is placed last so the static prefix is cacheable upstream)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_HEADING = re.compile(r"^# (.+)$", re.MULTILINE)


def _parse(name: str) -> tuple[dict[str, str], dict[str, str]]:
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    match = _FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"prompts/{name}.md is missing front matter")
    meta = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    meta = {key.strip(): value.strip() for key, value in meta.items()}
    body = text[match.end():]
    headings = list(_HEADING.finditer(body))
    sections = {heading.group(1).strip(): body[heading.end():(headings[i + 1].start() if i + 1 < len(headings) else len(body))].strip() for i, heading in enumerate(headings)}
    return meta, sections


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user: Template

    @property
    def PROMPT_VERSION(self) -> str:  # noqa: N802 - named as the constant it represents
        return f"{self.name}@{self.version}"

    def render(self, **variables: object) -> str:
        return self.user.substitute(**{key: str(value) for key, value in variables.items()})


def load_prompt(name: str) -> Prompt:
    meta, sections = _parse(name)
    if "System" not in sections or "User" not in sections:
        raise ValueError(f"prompts/{name}.md needs '# System' and '# User' sections")
    return Prompt(name=meta.get("name", name), version=meta["version"], system=sections["System"], user=Template(sections["User"]))


def load_sections(name: str) -> dict[str, str]:
    return _parse(name)[1]


EXTRACT_CLAIMS = load_prompt("extract_claims")
JUDGE_RELEVANCE = load_prompt("judge_relevance")
JUDGE_COVERAGE = load_prompt("judge_coverage")
GENERATE_CORPUS = load_prompt("generate_corpus")
MODERATE = load_prompt("moderate")
FIELD_INTENTS: dict[str, str] = load_sections("field_intents")
