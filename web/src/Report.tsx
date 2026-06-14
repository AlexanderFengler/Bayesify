import type { FixItem, PaperState, ScoredResult, StepAssessment, StepStatus } from "./types";

const STEP_NAMES: Record<string, string> = {
  S1: "Model specification & justification",
  S2: "Prior specification",
  S3: "Prior predictive checks",
  S4: "Computational faithfulness (convergence & diagnostics)",
  S5: "Posterior predictive checks",
  S6: "Model comparison / selection",
  S7: "Simulation-based calibration",
  S8: "Prior / model sensitivity analysis",
  S9: "Reporting & reproducibility",
  S10: "Posterior summary & inference communication",
};

const STATUS_LABEL: Record<StepStatus, string> = {
  done_well: "done well",
  partial: "partial",
  missing: "missing",
  not_applicable: "not applicable",
};

export function Report({ paper, onReset }: { paper: PaperState; onReset: () => void }) {
  const r = paper.result!;
  if (r.relevance.label === "no") {
    return <NotApplicable paper={paper} onReset={onReset} />;
  }
  return (
    <div className="report">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">
            Report <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
          </div>
          <h1 className="report-title">{paper.source_label}</h1>
        </div>
        <div className="report-head-actions">
          <Downloads paperId={paper.paper_id} />
          <button className="btn" onClick={onReset}>
            Analyze another
          </button>
        </div>
      </div>

      <SummaryBand r={r} />
      <RelevanceLine r={r} />
      <PriorityFixes fixes={paper.fix_list} />

      <div className="steps">
        {r.step_assessments.map((a) => (
          <StepCard key={a.step_id} a={a} />
        ))}
      </div>

      <ProvenanceFooter r={r} />
    </div>
  );
}

// Who produced this result. The clearest "the model actually ran" signal — a real backend
// (subscription / API) vs the labelled stub that runs when no credentials are configured.
function BackendBadge({ backend, fromCache }: { backend: string | null; fromCache: boolean }) {
  if (!backend) return null;
  if (backend === "stub") {
    return <span className="backend-badge be-stub">Stub engine · no model</span>;
  }
  const name =
    backend === "agent-sdk" ? "Claude subscription" : backend === "api" ? "Anthropic API" : backend;
  // A cache replay is labelled distinctly from a fresh live run, so a hit never masquerades as live.
  if (fromCache) {
    return <span className="backend-badge be-cache">Cached · {name}</span>;
  }
  return <span className="backend-badge be-live">Live · {name}</span>;
}

function Downloads({ paperId }: { paperId: string }) {
  return (
    <span className="report-downloads">
      <a href={`/api/papers/${paperId}/report.json`} target="_blank" rel="noreferrer">
        report.json
      </a>
      <a href={`/api/papers/${paperId}/report.md`} target="_blank" rel="noreferrer">
        report.md
      </a>
    </span>
  );
}

// D2: the prioritized fix-list across all steps (severity → step weight → ease), each with the
// verified score-impact of fixing it. Ranked server-side; this just renders.
function PriorityFixes({ fixes }: { fixes: FixItem[] | null }) {
  if (!fixes || fixes.length === 0) return null;
  return (
    <div className="fixes">
      <div className="grounding-label">Priority fixes</div>
      {fixes.map((f, i) => (
        <div key={i} className={"fix sev-" + f.severity}>
          <div className="fix-head">
            <span className={"sev-tag sev-" + f.severity}>{f.severity}</span>
            <span className="fix-step">{f.step_id}</span>
            <span className="fix-text">{f.text}</span>
            <span className="ease" title="estimated effort">
              {f.ease} effort
            </span>
          </div>
          <div className="how-to">{f.how_to}</div>
          {f.coverage_delta > 0 && (
            <div className="fix-impact">
              fixing this lifts coverage by {(f.coverage_delta * 100).toFixed(0)} pts
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// The model's own relevance verdict + rationale — for a live run this reflects THIS paper; the stub
// always shows its fixed HDDM sentence, so this is how you see the screen stage actually ran.
function RelevanceLine({ r }: { r: ScoredResult }) {
  return (
    <div className="relevance-line">
      <span className="grounding-label">Relevance gate</span>
      <p className="rl-text">
        <span className={"status-pill status-" + (r.relevance.label === "yes" ? "done_well" : "partial")}>
          {r.relevance.label}
        </span>
        <span className="rl-conf">{Math.round(r.relevance.confidence * 100)}% conf.</span>
        {r.relevance.rationale}
      </p>
    </div>
  );
}

function SummaryBand({ r }: { r: ScoredResult }) {
  const cov = r.coverage;
  let coverageText = "—";
  let rangeNote: string | null = null;
  if (cov) {
    const lo = Math.round(cov.strict * cov.applicable);
    const hi = Math.round(cov.lenient * cov.applicable);
    coverageText = lo === hi ? `${lo}` : `${lo}–${hi}`;
    rangeNote = lo === hi ? null : "range reflects low-confidence absences";
  }
  const quality = r.quality_score;
  return (
    <div className="summary">
      <div className="metric metric-primary">
        <div className="metric-value">
          {coverageText}
          {cov && <span className="metric-denom">/ {cov.applicable}</span>}
        </div>
        <div className="metric-label">applicable steps present</div>
        {rangeNote && <div className="metric-note">{rangeNote}</div>}
      </div>
      <div className="metric">
        <div className="metric-value">{quality == null ? "—" : quality.toFixed(2)}</div>
        <div className="metric-label">quality score</div>
        {quality != null && (
          <div className="qbar">
            <span style={{ width: `${Math.round(quality * 100)}%` }} />
          </div>
        )}
      </div>
      <div className="chips">
        <Chip k="relevance" v={r.relevance.label} />
        {r.paper_class && <Chip k="paper type" v={r.paper_class.primary.replace(/_/g, " ")} />}
        <Chip k="rubric profile" v={r.rubric_profile} />
      </div>
    </div>
  );
}

function Chip({ k, v }: { k: string; v: string }) {
  return (
    <div className="chip">
      <span className="chip-k">{k}</span>
      <span className="chip-v">{v}</span>
    </div>
  );
}

function StepCard({ a }: { a: StepAssessment }) {
  const na = a.status === "not_applicable";
  return (
    <section className={"step-card status-" + a.status}>
      <header className="step-card-head">
        <span className={"status-pill status-" + a.status}>{STATUS_LABEL[a.status]}</span>
        <div className="step-heading">
          <span className="step-id">{a.step_id}</span>
          <span className="step-name">{STEP_NAMES[a.step_id] ?? a.step_id}</span>
        </div>
        {!na && <Confidence value={a.confidence} />}
      </header>

      {na ? (
        <p className="na-reason">{a.applicability_reason}</p>
      ) : (
        <div className="step-body">
          {a.did_well.length > 0 && (
            <ul className="did-well">
              {a.did_well.map((d, i) => (
                <li key={i}>
                  <span className="tick">✓</span>
                  {d}
                </li>
              ))}
            </ul>
          )}

          {a.suggestions.map((sug, i) => (
            <div key={i} className={"suggestion sev-" + sug.severity}>
              <div className="suggestion-head">
                <span className={"sev-tag sev-" + sug.severity}>{sug.severity}</span>
                <span className="suggestion-text">{sug.text}</span>
                <span className="ease" title="estimated effort to fix">
                  {sug.ease} effort
                </span>
              </div>
              <div className="how-to">{sug.how_to}</div>
            </div>
          ))}

          {a.evidence.filter((e) => e.kind !== "absence_search").length > 0 && (
            <div className="grounding">
              <div className="grounding-label">In the paper</div>
              {a.evidence
                .filter((e) => e.kind !== "absence_search")
                .map((e, i) => (
                  <blockquote key={i} className="evidence">
                    &ldquo;{e.span.quote}&rdquo;
                    <cite>
                      §{e.span.section_id}
                      {e.span.page != null && `, p.${e.span.page}`}
                    </cite>
                  </blockquote>
                ))}
            </div>
          )}

          {a.standards.length > 0 && (
            <div className="grounding">
              <div className="grounding-label">Standard applied</div>
              <div className="standards">
                {a.standards.map((s, i) => (
                  <span key={i} className="standard" title={s.verified ? "verified in the research run" : "cited; not independently verified in the research run"}>
                    {s.citation}
                    {s.locator && <span className="locator"> · {s.locator}</span>}
                    <span className={"verif " + (s.verified ? "ok" : "unv")}>
                      {s.verified ? "✓ verified" : "unverified"}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {a.adversarial_verdict?.challenged && (
            <div className="adversarial">
              <span className="adv-label">Adversarial check</span> {a.adversarial_verdict.notes}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Confidence({ value }: { value: number }) {
  return (
    <span className="confidence" title="engine confidence (uncalibrated at this milestone)">
      {Math.round(value * 100)}% conf.
    </span>
  );
}

function NotApplicable({ paper, onReset }: { paper: PaperState; onReset: () => void }) {
  const r = paper.result!;
  return (
    <div className="report">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">
            Relevance gate <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
          </div>
          <h1 className="report-title">{paper.source_label}</h1>
        </div>
        <button className="btn" onClick={onReset}>
          Analyze another
        </button>
      </div>

      <div className="card na-card">
        <div className="na-badge">This doesn&rsquo;t appear to apply</div>
        <p className="na-lead">
          The relevance gate found no Bayesian statistical methodology to assess, so no per-step
          report was produced &mdash; <strong>nothing was graded</strong>.
        </p>
        <div className="na-why">
          <div className="grounding-label">Why</div>
          <p>{r.relevance.rationale}</p>
          <div className="na-conf">gate confidence {Math.round(r.relevance.confidence * 100)}%</div>
        </div>
        <p className="na-foot">
          If you believe this is a Bayesian paper, the detector inventory and a forced re-run will
          arrive with the full report UX (M6).
        </p>
      </div>

      <ProvenanceFooter r={r} />
    </div>
  );
}

function ProvenanceFooter({ r }: { r: ScoredResult }) {
  const validated = r.validation_ref !== "unvalidated";
  return (
    <div className="provenance">
      <div className="prov-row">
        <span>engine {r.engine_version}</span>
        <span>
          rubric {r.rubric_version} · {r.rubric_profile}
        </span>
        <span>${r.cost_ledger.total_cost_usd.toFixed(3)}</span>
      </div>
      <div className={"validation-note " + (validated ? "" : "preliminary")}>
        {validated
          ? `development-set agreement applies (${r.validation_ref})`
          : "preliminary — the engine is not yet validated against expert ratings (validation runs at M7)."}
      </div>
    </div>
  );
}
