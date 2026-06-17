import { useState } from "react";
import { recordOverride } from "./api";
import { STATUS_LABEL, STATUS_OPTIONS, useRubric, useStepNames } from "./rubric";
import { EvidenceBlock, StepCardShell } from "./StepCard";
import type { FixItem, PaperState, ScoredResult, StepAssessment, StepStatus } from "./types";

export function Report({
  paper,
  onReset,
  onRerun,
}: {
  paper: PaperState;
  onReset: () => void;
  onRerun: (paperId: string) => void;
}) {
  const r = paper.result!;
  // Records of expert disagreements made this session (step_id -> corrected status). Purely a UI
  // indicator; the engine output is never mutated (A5).
  const [overrides, setOverrides] = useState<Record<string, StepStatus>>({});
  const rubric = useRubric(r.rubric_profile); // the rubric this paper was graded against
  const stepNames = useStepNames(r.rubric_profile);
  if (r.relevance.label === "no" || r.not_applicable_reason) {
    return <NotApplicable paper={paper} onReset={onReset} onRerun={onRerun} />;
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

      {r.relevance.overridden && (
        <div className="override-banner">
          Graded on request. The relevance gate did not classify this as a Bayesian paper; you asked
          for a full assessment anyway, so treat coverage and quality as provisional.
        </div>
      )}

      {rubric && (
        <p className="rubric-preamble">
          <strong>{rubric.label}.</strong> {rubric.summary}
        </p>
      )}
      <SummaryBand r={r} />
      <StepStrip steps={r.step_assessments} stepNames={stepNames} />
      <RelevanceLine r={r} />

      <h2 className="section-title">Full report</h2>
      <div className="steps">
        {r.step_assessments.map((a) => (
          <StepCard
            key={a.step_id}
            a={a}
            stepName={stepNames[a.step_id] ?? a.step_id}
            overridden={overrides[a.step_id]}
            onOverride={async (status, rationale) => {
              await recordOverride(paper.paper_id, a.step_id, status, rationale);
              setOverrides((prev) => ({ ...prev, [a.step_id]: status }));
            }}
          />
        ))}
      </div>

      <SummarySection r={r} fixes={paper.fix_list} />
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

// End-of-report recap: a one-line takeaway built from the same data, then the prioritized fixes
// (moved here from the top — the fixes are the closing "what to do", not the opening).
function SummarySection({ r, fixes }: { r: ScoredResult; fixes: FixItem[] | null }) {
  const cov = r.coverage;
  const needsAttention = r.step_assessments.filter(
    (a) => a.status === "missing" || a.status === "partial",
  ).length;
  const quality = r.quality_score;
  return (
    <div className="report-summary">
      <div className="grounding-label">Summary</div>
      <p className="summary-recap">
        {cov ? (
          <>
            <strong>
              {cov.present} of {cov.applicable}
            </strong>{" "}
            applicable steps present
            {quality != null && (
              <>
                {" · quality "}
                <strong>{quality.toFixed(2)}</strong>
              </>
            )}
            {needsAttention > 0 ? (
              <>
                {" · "}
                <strong>{needsAttention}</strong> step{needsAttention === 1 ? "" : "s"} to improve
              </>
            ) : (
              " · nothing flagged"
            )}
            .
          </>
        ) : (
          "No applicable steps to summarize."
        )}
      </p>
      <PriorityFixes fixes={fixes} />
    </div>
  );
}

const COVERAGE_HELP =
  "Coverage = the share of APPLICABLE steps that are present at all (done well or partial). " +
  "N/A steps are excluded from the denominator. The range (e.g. 6–7) reflects low-confidence " +
  "absences: the low end counts them absent, the high end counts them present.";

const QUALITY_HELP =
  "Quality = average credit across the applicable steps: done well = 1, partial = ½, missing = 0 " +
  "(N/A excluded), as a weighted mean (v0 weights every step equally). It measures how WELL each " +
  "step was done, so it sits at or below coverage — partial steps count toward coverage but only " +
  "score ½ here, and missing steps score 0.";

// A small hover/focus tooltip (native title) for explaining a metric in place.
function InfoDot({ text }: { text: string }) {
  return (
    <span className="info-dot" tabIndex={0} role="note" aria-label={text} title={text}>
      &#9432;
    </span>
  );
}

const STATUS_GLYPH: Record<StepStatus, string> = {
  done_well: "✓",
  partial: "◐",
  missing: "✗",
  not_applicable: "–",
};
const STRIP_LEGEND: StepStatus[] = ["done_well", "partial", "missing", "not_applicable"];

// Item 1: a 2-second pictorial of every step's status — colour-coded cells, click to jump to a step.
function StepStrip({
  steps,
  stepNames,
}: {
  steps: StepAssessment[];
  stepNames: Record<string, string>;
}) {
  if (steps.length === 0) return null;
  return (
    <div className="step-strip">
      <div className="grounding-label">Steps at a glance</div>
      <div className="strip-row">
        {steps.map((a) => (
          <a
            key={a.step_id}
            href={`#step-${a.step_id}`}
            className={"strip-cell status-" + a.status}
            title={`${a.step_id} · ${stepNames[a.step_id] ?? a.step_id} — ${STATUS_LABEL[a.status]}`}
          >
            <span className="strip-id">{a.step_id}</span>
            <span className="strip-glyph">{STATUS_GLYPH[a.status]}</span>
          </a>
        ))}
      </div>
      <div className="strip-legend">
        {STRIP_LEGEND.map((s) => (
          <span key={s} className="lg">
            <span className={"dot status-" + s} />
            {STATUS_LABEL[s]}
          </span>
        ))}
      </div>
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
  const total = r.step_assessments.length;
  const naCount = cov ? total - cov.applicable : 0;
  return (
    <div className="summary">
      <div className="metric metric-primary">
        <div className="metric-value">
          {coverageText}
          {cov && <span className="metric-denom">/ {cov.applicable}</span>}
        </div>
        <div className="metric-label">
          applicable steps present
          <InfoDot text={COVERAGE_HELP} />
        </div>
        {cov && naCount > 0 && (
          <div className="metric-note">
            {naCount} of {total} steps not applicable (excluded from the denominator)
          </div>
        )}
        {rangeNote && <div className="metric-note">{rangeNote}</div>}
      </div>
      <div className="metric">
        <div className="metric-value">{quality == null ? "—" : quality.toFixed(2)}</div>
        <div className="metric-label">
          quality score
          <InfoDot text={QUALITY_HELP} />
        </div>
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

function StepCard({
  a,
  stepName,
  overridden,
  onOverride,
}: {
  a: StepAssessment;
  stepName: string;
  overridden?: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
  const na = a.status === "not_applicable";
  return (
    <StepCardShell
      stepId={a.step_id}
      stepName={stepName}
      sectionClass={"status-" + a.status}
      sectionId={"step-" + a.step_id}
      pill={<span className={"status-pill status-" + a.status}>{STATUS_LABEL[a.status]}</span>}
      headerRight={na ? undefined : <Confidence value={a.confidence} />}
    >
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

          <EvidenceBlock
            spans={a.evidence.filter((e) => e.kind !== "absence_search").map((e) => e.span)}
          />

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

          {overridden ? (
            <div className="override-chip">
              Expert override recorded: <strong>{STATUS_LABEL[overridden]}</strong>
              <span className="override-note">
                recorded for the v1 learning loop — not yet used to change judgments
              </span>
            </div>
          ) : (
            <DisagreeControl currentStatus={a.status} onOverride={onOverride} />
          )}
        </div>
      )}
    </StepCardShell>
  );
}

function DisagreeControl({
  currentStatus,
  onOverride,
}: {
  currentStatus: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<StepStatus>(currentStatus);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button className="link-btn disagree" onClick={() => setOpen(true)}>
        Disagree?
      </button>
    );
  }
  return (
    <div className="disagree-form">
      <label>
        Corrected status
        <select value={status} onChange={(e) => setStatus(e.target.value as StepStatus)}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      <textarea
        placeholder="Why? (optional rationale — recorded, not used to change the judgment)"
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
      />
      <div className="disagree-actions">
        <button
          className="btn btn-primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onOverride(status, rationale);
            } finally {
              setBusy(false);
            }
          }}
        >
          Record override
        </button>
        <button className="link-btn" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function Confidence({ value }: { value: number }) {
  return (
    <span className="confidence" title="engine confidence (uncalibrated at this milestone)">
      {Math.round(value * 100)}% conf.
    </span>
  );
}

function NotApplicable({
  paper,
  onReset,
  onRerun,
}: {
  paper: PaperState;
  onReset: () => void;
  onRerun: (paperId: string) => void;
}) {
  const r = paper.result!;
  const [busy, setBusy] = useState(false);
  // Two short-circuit reasons share this page: a not-Bayesian paper (the relevance gate) and a
  // review/opinion piece the per-step rubric doesn't apply to.
  const isReview = r.not_applicable_reason === "not_an_application";
  return (
    <div className="report">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">
            {isReview ? "Paper type" : "Relevance gate"}{" "}
            <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
          </div>
          <h1 className="report-title">{paper.source_label}</h1>
        </div>
        <button className="btn" onClick={onReset}>
          Analyze another
        </button>
      </div>

      <div className="card na-card">
        <div className="na-badge">
          {isReview ? "The per-step rubric doesn’t apply here" : "This doesn’t appear to apply"}
        </div>
        <p className="na-lead">
          {isReview ? (
            <>
              This reads as a review / opinion / perspective piece <em>about</em> the Bayesian
              workflow. The per-step rubric grades papers that <strong>apply</strong> a workflow to
              data, so it doesn&rsquo;t directly apply &mdash; <strong>nothing was graded</strong>.
            </>
          ) : (
            <>
              The relevance gate found no Bayesian statistical methodology to assess, so no per-step
              report was produced &mdash; <strong>nothing was graded</strong>.
            </>
          )}
        </p>
        <div className="na-why">
          <div className="grounding-label">Why</div>
          <p>{(isReview && r.paper_class?.rationale) || r.relevance.rationale}</p>
          <div className="na-conf">
            {isReview && r.paper_class
              ? `classified ${r.paper_class.primary} · ${Math.round(r.paper_class.confidence * 100)}%`
              : `gate confidence ${Math.round(r.relevance.confidence * 100)}%`}
          </div>
        </div>
        <div className="na-escape">
          <p className="na-foot">
            {isReview
              ? "If you want the per-step grade anyway, you can run it as an advisory assessment. " +
                "It's recorded; coverage and quality will be marked provisional."
              : "If you believe this is a Bayesian paper, you can override the gate and grade it " +
                "anyway. The override is recorded; coverage and quality will be marked provisional."}
          </p>
          <button
            className="btn btn-primary"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              onRerun(paper.paper_id);
            }}
          >
            {busy ? "Re-running…" : "Run full assessment anyway"}
          </button>
        </div>
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
