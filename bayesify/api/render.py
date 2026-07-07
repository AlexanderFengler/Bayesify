"""Markdown renderers for API export endpoints."""

from __future__ import annotations

from bayesify.api.jobs import Job
from bayesify.core.report import fix_list


def render_markdown(job: Job) -> str:
    result = job.result
    assert result is not None
    paper_types = (
        ", ".join(label.value for label in result.paper_class.labels)
        if result.paper_class
        else "n/a"
    )
    weights = {p.step_id: p.weight for p in result.profile.steps} if result.profile else {}
    lines = [f"# Bayesify report - {job.source_label}", ""]
    if result.coverage:
        lo, hi = (
            round(result.coverage.strict * result.coverage.applicable),
            round(result.coverage.lenient * result.coverage.applicable),
        )
        rng = f"{lo}" if lo == hi else f"{lo}-{hi}"
        lines.append(f"**Coverage:** {rng} / {result.coverage.applicable} applicable steps present")
    if result.quality_score is not None:
        lines.append(
            f"**Quality:** {result.quality_score} "
            "_(weighted mean of sub-scores over applicable steps; per-step weights below)_"
        )
    lines += [
        f"**Relevance:** {result.relevance.label.value} . **Paper type:** "
        f"{paper_types} . "
        f"**Profile:** {result.rubric_profile}",
        "",
    ]
    fixes = fix_list(result)
    if fixes:
        lines.append("## Priority fixes")
        for fix in fixes:
            lines.append(
                f"- [{fix.severity.value}] {fix.step_id}: {fix.text} "
                f"- _{fix.how_to}_ ({fix.ease.value} effort)"
            )
        lines.append("")
    for assessment in result.step_assessments:
        weight = weights.get(assessment.step_id)
        suffix = f" . weight {weight}" if assessment.applicable and weight is not None else ""
        lines.append(f"## {assessment.step_id} - {assessment.status.value}{suffix}")
        for praise in assessment.did_well:
            lines.append(f"- OK: {praise}")
        for suggestion in assessment.suggestions:
            lines.append(f"- [{suggestion.severity.value}] {suggestion.text}")
        lines.append("")
    lines.append(
        f"_Engine {result.engine_version} . rubric {result.rubric_version} . "
        f"${result.cost_ledger.total_cost_usd} . {result.validation_ref}. "
        "Formative report, not a verdict._"
    )
    return "\n".join(lines)


def render_inventory_markdown(job: Job) -> str:
    inventory = job.inventory
    assert inventory is not None
    lines = [
        f"# Bayesify - local detection report - {job.source_label}",
        "",
        f"_Detection only, not graded. Parser: {job.parser} ({job.parser_version}). "
        f"{inventory.n_hits} signals detected. No LLM; nothing left this machine._",
        "",
    ]
    for family in inventory.families:
        lines.append(f"## {family.family.replace('_', ' ')}")
        if family.found:
            for hit in family.found:
                value = f" - `{hit.value}`" if hit.value else ""
                page = f", p.{hit.page}" if hit.page is not None else ""
                lines.append(
                    f'- **{hit.detector_id}**{value}: "{hit.quote}" '
                    f"(section {hit.section_id}{page})"
                )
        if family.not_detected:
            lines.append(f"- _not detected: {', '.join(family.not_detected)}_")
        lines.append("")
    looked = ", ".join(
        f"{section.kind.value} ({section.title})" for section in inventory.where_looked
    ) or "-"
    skipped = ", ".join(section.title for section in inventory.skipped) or "none"
    lines += [
        "## Where the engine looked",
        f"Scanned: {looked}.",
        f"Skipped (not scanned): {skipped}.",
    ]
    return "\n".join(lines)
