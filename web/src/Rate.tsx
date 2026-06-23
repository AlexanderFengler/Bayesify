import { useEffect, useState } from "react";
import {
  fetchRateContext,
  fetchRubrics,
  type RateContext,
  type RatingInput,
  type RubricSummary,
  submitRating,
} from "./api";
import { STATUS_LABEL, STATUS_OPTIONS } from "./rubric";
import { StepCardShell } from "./StepCard";
import type { StepStatus } from "./types";

type Relevance = "" | "yes" | "partial" | "no";
type PaperClass =
  | "model_development"
  | "method_development"
  | "software_development"
  | "data_analysis"
  | "numerical_analysis"
  | "theoretical_analysis"
  | "review";

interface StepDraft {
  status: "" | StepStatus;
  confidence: number;
  rationale: string;
  cited: number[]; // indices into ctx.evidence
  missingSubtag: "" | "not-done" | "not-reported-suspected";
}
const EMPTY: StepDraft = { status: "", confidence: 0.8, rationale: "", cited: [], missingSubtag: "" };

const INFERENCE = ["mcmc", "hmc_nuts", "variational", "sbi", "exact_analytic", "unstated"];
const PRIORS = ["informative", "weakly_informative", "default", "none", "unstated"];
const CLASSES: { v: PaperClass; label: string }[] = [
  { v: "model_development", label: "model development" },
  { v: "method_development", label: "method development" },
  { v: "software_development", label: "software development" },
  { v: "data_analysis", label: "data analysis" },
  { v: "numerical_analysis", label: "numerical analysis" },
  { v: "theoretical_analysis", label: "theoretical analysis" },
  { v: "review", label: "review / tutorial / commentary" },
];

// The blind rating form: a rater walks the same rubric the engine walks and authors a Rating,
// WITHOUT ever seeing the engine's verdict (the context endpoint serves no ScoredResult). Statuses
// start blank — nothing is pre-filled from the engine or the gate resolver, so the rater judges cold.
export function Rate({ paperId, onExit }: { paperId: string; onExit: () => void }) {
  const [ctx, setCtx] = useState<RateContext | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [profile, setProfile] = useState("synthesis"); // which rubric the rater rates against
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [raterId, setRaterId] = useState("rater-1");
  const [relationship, setRelationship] = useState("independent");
  const [relevance, setRelevance] = useState<Relevance>("");
  const [relevanceRationale, setRelevanceRationale] = useState("");
  const [paperClasses, setPaperClasses] = useState<PaperClass[]>([]);
  const [classRationale, setClassRationale] = useState("");
  const [gate, setGate] = useState({
    inference_method: "mcmc",
    n_models: 1,
    bf_claimed: false,
    prior_informativeness: "weakly_informative",
  });
  const [perStep, setPerStep] = useState<Record<string, StepDraft>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    fetchRubrics()
      .then(setRubrics)
      .catch(() => {});
  }, []);

  useEffect(() => {
    setCtx(null);
    setPerStep({}); // a different rubric has different steps — clear stale per-step drafts
    fetchRateContext(paperId, profile)
      .then(setCtx)
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));
  }, [paperId, profile]);

  const draft = (id: string) => perStep[id] ?? EMPTY;
  const setStep = (id: string, patch: Partial<StepDraft>) =>
    setPerStep((prev) => ({ ...prev, [id]: { ...(prev[id] ?? EMPTY), ...patch } }));
  const toggleCite = (id: string, i: number) => {
    const cur = draft(id).cited;
    setStep(id, { cited: cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i] });
  };
  const togglePaperClass = (klass: PaperClass) => {
    setPaperClasses((prev) =>
      prev.includes(klass) ? prev.filter((v) => v !== klass) : [...prev, klass],
    );
  };

  function build(): RatingInput | { error: string } {
    if (!relevance) return { error: "Choose a relevance verdict." };
    if (!relevanceRationale.trim()) return { error: "Add a relevance rationale." };
    const base = { rater_id: raterId.trim() || "rater-1", relationship };
    if (relevance === "no") {
      return {
        ...base,
        relevance_label: "no",
        relevance_rationale: relevanceRationale,
        paper_class_labels: [],
        paper_class_rationale: "",
        gate_facts: null,
        steps: [],
      };
    }
    if (paperClasses.length === 0) return { error: "Choose at least one paper type." };
    const steps = [];
    for (const s of ctx!.rubric.steps) {
      const d = draft(s.id);
      if (!d.status) continue; // an unrated step is omitted (a partial pass is allowed)
      const applicable = d.status !== "not_applicable";
      if (applicable && !d.rationale.trim()) return { error: `${s.id}: add a rationale.` };
      if ((d.status === "adequate" || d.status === "partial") && d.cited.length === 0)
        return { error: `${s.id}: cite ≥1 evidence span for a "${STATUS_LABEL[d.status]}" rating.` };
      steps.push({
        step_id: s.id,
        applicable,
        status: d.status,
        confidence: d.confidence,
        rationale: applicable ? d.rationale : "",
        evidence: d.cited.map((i) => ({
          section_id: ctx!.evidence[i].section_id,
          page: ctx!.evidence[i].page,
          quote: ctx!.evidence[i].quote,
        })),
        missing_subtag: d.status === "missing" && d.missingSubtag ? d.missingSubtag : null,
      });
    }
    if (steps.length === 0) return { error: "Rate at least one step." };
    return {
      ...base,
      relevance_label: relevance,
      relevance_rationale: relevanceRationale,
      paper_class_labels: paperClasses,
      paper_class_rationale: classRationale,
      gate_facts: gate,
      steps,
    };
  }

  async function onSubmit() {
    const r = build();
    if ("error" in r) {
      setFormError(r.error);
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      await submitRating(paperId, r, profile);
      setDone(true);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loadErr) {
    return (
      <div className="report">
        <div className="card error-card">
          <h2>Couldn&rsquo;t load the rating context</h2>
          <p>{loadErr}</p>
          <button className="btn" onClick={onExit}>
            Back
          </button>
        </div>
      </div>
    );
  }
  if (!ctx) return <div className="card">Loading…</div>;

  if (done) {
    return (
      <div className="report">
        <div className="card na-card">
          <div className="na-badge">Rating recorded</div>
          <p className="na-lead">
            Your blind rating of <strong>{ctx.source_label}</strong> was saved. Two-to-three blind
            ratings plus an adjudicated consensus assemble into the gold record (at adjudication).
          </p>
          <button className="btn btn-primary" onClick={onExit}>
            Done
          </button>
        </div>
      </div>
    );
  }

  const relevant = relevance !== "" && relevance !== "no";
  return (
    <div className="report rate">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">Blind rating</div>
          <h1 className="report-title">{ctx.source_label}</h1>
        </div>
        <button className="btn" onClick={onExit}>
          Cancel
        </button>
      </div>

      <div className="rate-blind-banner">
        You are rating <strong>blind</strong> — the engine&rsquo;s verdict is hidden. Judge each step
        from the paper and the detected evidence only; nothing here is pre-filled.
      </div>

      <div className="card rate-gate">
        <div className="rate-field">
          <label>
            Rubric
            <select value={profile} onChange={(e) => setProfile(e.target.value)}>
              {(rubrics.length ? rubrics : [{ id: profile, label: profile }]).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {ctx.rubric.summary && <p className="rubric-preamble">{ctx.rubric.summary}</p>}

        <div className="rate-field">
          <label>
            Rater id
            <input value={raterId} onChange={(e) => setRaterId(e.target.value)} />
          </label>
          <label>
            Relationship
            <select value={relationship} onChange={(e) => setRelationship(e.target.value)}>
              <option value="independent">independent</option>
              <option value="engine_dev">engine developer</option>
              <option value="prompt_author">prompt author</option>
            </select>
          </label>
        </div>

        <div className="rate-field">
          <label>
            Relevance - is Bayesian workflow applicable?
            <select value={relevance} onChange={(e) => setRelevance(e.target.value as Relevance)}>
              <option value="">— choose —</option>
              <option value="yes">yes</option>
              <option value="partial">partial</option>
              <option value="no">no</option>
            </select>
          </label>
        </div>
        <textarea
          className="rate-rationale"
          placeholder="Why? (required)"
          value={relevanceRationale}
          onChange={(e) => setRelevanceRationale(e.target.value)}
        />

        {relevant && (
          <>
            <div className="rate-field">
              <fieldset className="rate-class-field">
                <legend>Paper type</legend>
                <div className="rate-class-options">
                  {CLASSES.map((c) => (
                    <label key={c.v} className="rate-check">
                      <input
                        type="checkbox"
                        checked={paperClasses.includes(c.v)}
                        onChange={() => togglePaperClass(c.v)}
                      />
                      {c.label}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
            <textarea
              className="rate-rationale"
              placeholder="Why these paper types? (optional)"
              value={classRationale}
              onChange={(e) => setClassRationale(e.target.value)}
            />
            <div className="rate-field rate-gate-facts">
              <label>
                Inference
                <select
                  value={gate.inference_method}
                  onChange={(e) => setGate({ ...gate, inference_method: e.target.value })}
                >
                  {INFERENCE.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                # models
                <input
                  type="number"
                  min={1}
                  value={gate.n_models}
                  onChange={(e) => setGate({ ...gate, n_models: Math.max(1, +e.target.value) })}
                />
              </label>
              <label className="rate-check">
                <input
                  type="checkbox"
                  checked={gate.bf_claimed}
                  onChange={(e) => setGate({ ...gate, bf_claimed: e.target.checked })}
                />
                Bayes factor claimed
              </label>
              <label>
                Priors
                <select
                  value={gate.prior_informativeness}
                  onChange={(e) => setGate({ ...gate, prior_informativeness: e.target.value })}
                >
                  {PRIORS.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </>
        )}
      </div>

      {relevance === "no" && (
        <p className="rate-hint">
          Marked not a Bayesian-workflow paper — there are no steps to rate. Submit to record it.
        </p>
      )}

      {relevant && (
        <div className="steps">
          {ctx.rubric.steps.map((s) => {
            const d = draft(s.id);
            const na = d.status === "not_applicable";
            return (
              <StepCardShell
                key={s.id}
                stepId={s.id}
                stepName={s.name}
                sectionClass={d.status ? "status-" + d.status : "rate-unrated"}
                pill={<span className="rate-step-pill">{d.status ? STATUS_LABEL[d.status] : "rate"}</span>}
              >
                <div className="rate-step-body">
                  {s.adequate && (
                    <p className="rate-guide">
                      <strong>Adequate:</strong> {s.adequate}
                    </p>
                  )}
                  {s.done_poorly && (
                    <p className="rate-guide rate-guide-poor">
                      <strong>Done poorly:</strong> {s.done_poorly}
                    </p>
                  )}

                  <select
                    className="rate-status"
                    value={d.status}
                    onChange={(e) => setStep(s.id, { status: e.target.value as StepStatus | "" })}
                  >
                    <option value="">— rate this step —</option>
                    {STATUS_OPTIONS.map((st) => (
                      <option key={st} value={st}>
                        {STATUS_LABEL[st]}
                      </option>
                    ))}
                  </select>

                  {d.status && !na && (
                    <>
                      <label className="rate-conf">
                        Confidence: {Math.round(d.confidence * 100)}%
                        <input
                          type="range"
                          min={0}
                          max={1}
                          step={0.05}
                          value={d.confidence}
                          onChange={(e) => setStep(s.id, { confidence: +e.target.value })}
                        />
                      </label>
                      <textarea
                        className="rate-rationale"
                        placeholder="Rationale (required)"
                        value={d.rationale}
                        onChange={(e) => setStep(s.id, { rationale: e.target.value })}
                      />
                      {(d.status === "adequate" || d.status === "partial") && (
                        <EvidenceCite
                          spans={ctx.evidence}
                          cited={d.cited}
                          onToggle={(i) => toggleCite(s.id, i)}
                        />
                      )}
                      {d.status === "missing" && (
                        <div className="rate-field">
                          <label>
                            Missing because
                            <select
                              value={d.missingSubtag}
                              onChange={(e) =>
                                setStep(s.id, { missingSubtag: e.target.value as StepDraft["missingSubtag"] })
                              }
                            >
                              <option value="">— optional —</option>
                              <option value="not-done">not done</option>
                              <option value="not-reported-suspected">done but not reported</option>
                            </select>
                          </label>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </StepCardShell>
            );
          })}
        </div>
      )}

      {formError && <div className="rate-error">{formError}</div>}
      <div className="rate-actions">
        <button className="btn btn-primary" disabled={submitting} onClick={onSubmit}>
          {submitting ? "Saving…" : "Submit blind rating"}
        </button>
      </div>
    </div>
  );
}

function EvidenceCite({
  spans,
  cited,
  onToggle,
}: {
  spans: RateContext["evidence"];
  cited: number[];
  onToggle: (i: number) => void;
}) {
  if (spans.length === 0) {
    return (
      <p className="rate-hint">
        No detector spans to cite for this paper. (Free-quote citation is a later enhancement.)
      </p>
    );
  }
  return (
    <div className="rate-cite">
      <div className="grounding-label">Cite the evidence you saw (≥1 for present)</div>
      {spans.map((e, i) => (
        <label key={i} className="rate-cite-item">
          <input type="checkbox" checked={cited.includes(i)} onChange={() => onToggle(i)} />
          <span>
            &ldquo;{e.quote}&rdquo; <cite>§{e.section_id}</cite>
          </span>
        </label>
      ))}
    </div>
  );
}
