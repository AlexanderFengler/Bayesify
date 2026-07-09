"""LLM paper-title + author extraction — a pre-grading metadata step.

A cheap-model structured call that recovers a clean title *and author list* from the first page when
no provider (arXiv / DOI / OpenAlex) metadata is available: the PDF heuristics in ``parse`` are weak
for uploads — the largest-font title heuristic misfires on odd layouts, and authors come only from
the embedded ``/Author`` field, which is frequently blank (e.g. LaTeX leaves it empty). When
a rendered first-page image is supplied it is sent alongside the text so a multimodal backend can
read the byline off the page a human sees, robust to two-column reading-order scrambling. Metadata
only — it never affects the grade, so its prompt is deliberately kept out of the graded
``engine_version`` fingerprint.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from bayesify.core.context import excerpt_context
from bayesify.core.schema import ParsedDoc
from bayesify.llm import LLMClient, call_with_policy
from bayesify.llm import config as llm_config

_TITLE_MAX_CHARS = 4_000  # the title + byline are on page 1 / the abstract, not the whole paper

EXTRACT_SYSTEM = """You extract the title and author list of an academic paper from its opening \
text and, when provided, an image of its first page. Return the title verbatim as printed (no \
venue, no "Title:" prefix, no quotation marks) and the authors as a list of full names in the \
order printed (given name first, no affiliations, degrees, or email addresses). Prefer the \
first-page image over the text when they disagree. Use an empty string / empty list for anything \
the page does not clearly show — never invent a title or an author."""


class PaperMetadata(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)


def extract_metadata(
    parsed: ParsedDoc,
    *,
    client: LLMClient,
    model: str | None = None,
    page_image: bytes | None = None,
    opening_text: str | None = None,
) -> PaperMetadata:
    """Extract the paper title + authors via a cheap structured LLM call, optionally multimodal (a
    rendered first-page PNG in ``page_image`` and/or the raw page-1 text in ``opening_text``).
    Prefer ``opening_text`` (raw page 1, with the title + byline) over ``excerpt_context``, which
    starts at the abstract and drops those lines. Returns a ``PaperMetadata`` (``title`` may be
    empty, ``authors`` may be ``[]``). Raises ``LLMError`` on transport failure; a miss is not fatal
    (the parse heuristics remain the fallback)."""
    model = model or llm_config.classify_model()
    text = opening_text if opening_text else excerpt_context(parsed, max_chars=_TITLE_MAX_CHARS)
    user = f"PAPER OPENING:\n{text[:_TITLE_MAX_CHARS]}"
    response = call_with_policy(
        client,
        model=model,
        system=EXTRACT_SYSTEM,
        user=user,
        schema=PaperMetadata,
        max_tokens=200,
        image=page_image,
    )
    meta = response.parsed
    return PaperMetadata(
        title=meta.title.strip(),
        authors=[a.strip() for a in meta.authors if a and a.strip()],
    )
