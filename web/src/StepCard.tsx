import type { ReactNode } from "react";
import type { EvidenceSpan } from "./types";

// Shared, blind-safe step-card atoms used by BOTH the engine report (Report.tsx) and the blind
// rating form (Rate.tsx). They carry no engine judgment of their own — each consumer passes its own
// pill/header/body in — so the rating form can reuse the layout without inheriting the engine's
// framing (the validity firewall).

// The frame + header (step-id + step-name) with a leading `pill` slot and a trailing `headerRight`
// slot, plus the body as children.
export function StepCardShell({
  stepId,
  stepName,
  sectionClass,
  sectionId,
  pill,
  headerRight,
  children,
}: {
  stepId: string;
  stepName: string;
  sectionClass?: string;
  sectionId?: string;
  pill?: ReactNode;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={sectionId} className={"step-card" + (sectionClass ? " " + sectionClass : "")}>
      <header className="step-card-head">
        {pill}
        <div className="step-heading">
          <span className="step-id">{stepId}</span>
          <span className="step-name">{stepName}</span>
        </div>
        {headerRight}
      </header>
      {children}
    </section>
  );
}

// The "In the paper" evidence panel over verbatim spans — collapsed by default (it's supporting
// detail, not the headline). Renders nothing when empty.
export function EvidenceBlock({
  spans,
  label = "In the paper",
}: {
  spans: EvidenceSpan[];
  label?: string;
}) {
  if (spans.length === 0) return null;
  return (
    <details className="grounding">
      <summary className="grounding-label">
        {label} ({spans.length})
      </summary>
      {spans.map((s, i) => (
        <blockquote key={i} className="evidence">
          &ldquo;{s.quote}&rdquo;
          <cite>
            §{s.section_id}
            {s.page != null && `, p.${s.page}`}
          </cite>
        </blockquote>
      ))}
    </details>
  );
}
