"""LLM paper-title extraction — a pre-grading metadata step.

A cheap-model structured call that recovers a clean title from the first-page text when no provider
(arXiv / DOI / OpenAlex) title is available: the PDF heuristic in ``parse`` (largest-font text on
page 1 / embedded ``/Title``) is weak for uploads. Metadata only — it never affects the grade, so
its prompt is deliberately kept out of the graded ``engine_version`` fingerprint.
"""

from __future__ import annotations

from pydantic import BaseModel

from bayesify.core.context import excerpt_context
from bayesify.core.schema import ParsedDoc
from bayesify.llm import LLMClient, call_with_policy
from bayesify.llm import config as llm_config

_TITLE_MAX_CHARS = 4_000  # the title is on page 1 / the abstract, not the whole paper

EXTRACT_SYSTEM = """You extract the title of an academic paper from its opening text. Return \
ONLY the paper's title, verbatim as printed — no authors, no venue, no "Title:" prefix, no \
quotation marks. If the opening text has no clear title, return an empty string."""


class PaperMetadata(BaseModel):
    title: str


def extract_metadata(
    parsed: ParsedDoc, *, client: LLMClient, model: str | None = None
) -> str | None:
    """Extract the paper title via a cheap structured LLM call. Returns the title, or ``None`` if
    the model returns nothing usable. Raises ``LLMError`` on transport failure; a title miss is not
    fatal (the parse heuristic remains as a fallback)."""
    model = model or llm_config.classify_model()
    user = f"PAPER OPENING:\n{excerpt_context(parsed, max_chars=_TITLE_MAX_CHARS)}"
    response = call_with_policy(
        client, model=model, system=EXTRACT_SYSTEM, user=user, schema=PaperMetadata, max_tokens=120
    )
    return response.parsed.title.strip() or None
