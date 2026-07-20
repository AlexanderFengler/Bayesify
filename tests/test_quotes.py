"""sentence_span — the endpoint chooser behind every EvidenceSpan.quote. The invariants: verbatim
substring, always contains the match, sentence-aligned whenever the cap allows."""

from __future__ import annotations

from bayesify.core.quotes import sentence_span

_TEXT = (
    "We fit a hierarchical model in Stan. All parameters had R-hat < 1.01 and bulk-ESS above "
    "1500. Posterior predictive checks reproduced the data."
)


def _span_of(needle: str, text: str = _TEXT) -> tuple[int, int]:
    i = text.index(needle)
    return i, i + len(needle)


def test_expands_to_the_enclosing_sentence() -> None:
    start, end = _span_of("R-hat < 1.01")
    q = sentence_span(_TEXT, start, end)
    assert q == "All parameters had R-hat < 1.01 and bulk-ESS above 1500."
    assert q in _TEXT  # verbatim substring guarantee


def test_decimals_do_not_split_sentences() -> None:
    # the dots inside "1.01" are followed by digits, not whitespace — no boundary there
    start, end = _span_of("bulk-ESS")
    assert sentence_span(_TEXT, start, end).startswith("All parameters had R-hat < 1.01")


def test_first_and_last_sentences_reach_text_edges() -> None:
    start, end = _span_of("Stan")
    assert sentence_span(_TEXT, start, end) == "We fit a hierarchical model in Stan."
    start, end = _span_of("reproduced")
    assert sentence_span(_TEXT, start, end) == "Posterior predictive checks reproduced the data."


def test_abbreviations_and_initials_do_not_split() -> None:
    text = "As shown by Gelman et al. the prior matters (see Fig. 3 and Eq. 2) for J. Doe's model."
    start, end = _span_of("prior", text)
    assert sentence_span(text, start, end) == text  # one sentence despite al./Fig./Eq./J.


def test_overlong_sentence_prefers_the_sentence_opening() -> None:
    text = "The sampler ran " + "with many settings " * 40 + "and finally converged."
    start, end = _span_of("sampler ran", text)
    q = sentence_span(text, start, end, max_chars=80)
    assert q.startswith("The sampler ran")  # sentence opening kept
    assert len(q) <= 80
    assert q in text


def test_overlong_sentence_still_contains_a_late_match() -> None:
    text = "The sampler ran " + "with many settings " * 40 + "and finally converged."
    start, end = _span_of("finally converged", text)
    q = sentence_span(text, start, end, max_chars=80)
    assert "finally converged" in q
    assert len(q) <= 80
    assert q in text


def test_match_ending_on_the_terminator_does_not_leak_into_the_next_sentence() -> None:
    start, _ = _span_of("We fit")
    end = _TEXT.index(".") + 1  # match includes the first sentence's terminator
    assert sentence_span(_TEXT, start, end) == "We fit a hierarchical model in Stan."


def test_zero_width_match_yields_the_first_sentence() -> None:
    # the absence-search quote: expand from the section start
    assert sentence_span(_TEXT, 0, 0) == "We fit a hierarchical model in Stan."
