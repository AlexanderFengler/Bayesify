import type { Rubric } from "./rubric";
import type { PaperState } from "./types";

// One fetch+parse helper for every JSON endpoint. `detail: true` surfaces the API's `{detail}`
// message (FastAPI 422s); otherwise a fixed `error` is thrown. (streamProgress uses EventSource,
// not this.)
async function fetchJson<T>(
  input: RequestInfo,
  init?: RequestInit,
  opts?: { error?: string; detail?: boolean },
): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    if (opts?.detail) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof body.detail === "string" ? body.detail : (opts.error ?? "request failed"));
    }
    throw new Error(opts?.error ?? "request failed");
  }
  return (await res.json()) as T;
}

export interface SubmitInput {
  file?: File | null;
  identifier?: string; // an arXiv ID / DOI / OpenAlex ID / URL
  mode: "full" | "local";
}

// Decide which form field an identifier belongs in (a thin client-side guess; the real resolver is
// the ingest component). Defaults to `url` so anything pasteable still reaches the backend.
function classifyIdentifier(raw: string): Record<string, string> {
  const v = raw.trim();
  if (/^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$/i.test(v)) return { arxiv_id: v.replace(/^arxiv:/i, "") };
  if (/^10\.\d{4,9}\//.test(v) || /doi\.org\//i.test(v)) return { doi: v };
  if (/^W\d+$/i.test(v) || /openalex\.org\//i.test(v)) return { openalex_id: v };
  return { url: v };
}

export async function submitPaper(input: SubmitInput): Promise<string> {
  const form = new FormData();
  form.set("mode", input.mode);
  if (input.file) form.set("file", input.file);
  else if (input.identifier) {
    for (const [k, val] of Object.entries(classifyIdentifier(input.identifier))) form.set(k, val);
  }
  const body = await fetchJson<{ paper_id: string }>(
    "/api/papers",
    { method: "POST", body: form },
    { detail: true, error: "upload failed" },
  );
  return body.paper_id;
}

export async function getPaper(paperId: string): Promise<PaperState> {
  return fetchJson<PaperState>(`/api/papers/${paperId}`, undefined, { error: "could not fetch paper" });
}

// Record an expert disagreement on one step (A5). Append-only; never mutates the engine output —
// "recorded for the v1 learning loop, not yet used to change judgments".
export async function recordOverride(
  paperId: string,
  stepId: string,
  correctedStatus: string,
  rationale: string,
): Promise<void> {
  const form = new FormData();
  form.set("corrected_status", correctedStatus);
  form.set("rationale", rationale);
  form.set("author", "you");
  await fetchJson(
    `/api/assessments/${paperId}/steps/${stepId}/override`,
    { method: "POST", body: form },
    { error: "could not record override" },
  );
}

// Re-run a short-circuited paper as 'partial' (the gate-page escape hatch). Returns the paper_id.
export async function rerun(paperId: string): Promise<string> {
  const form = new FormData();
  form.set("relevance_override", "partial");
  const body = await fetchJson<{ paper_id: string }>(
    `/api/papers/${paperId}/rerun`,
    { method: "POST", body: form },
    { error: "could not re-run" },
  );
  return body.paper_id;
}

// --- Blind expert rating (V3) ---------------------------------------------------------------------

export interface RateContextSpan {
  section_id: string;
  section_title: string;
  page: number | null;
  quote: string;
  family: string;
  detector_id: string;
  kind: string;
}
export interface RateContext {
  paper_id: string;
  source_label: string;
  source_sha256: string | null;
  rubric: Rubric;
  evidence: RateContextSpan[];
  where_looked: { section_id: string; title: string; kind: string; page: number | null }[];
}

// Load the BLIND rating context (rubric + detector evidence only — never the engine's ScoredResult).
export async function fetchRateContext(paperId: string): Promise<RateContext> {
  return fetchJson<RateContext>(`/api/rate/context/${paperId}`, undefined, {
    error: "could not load rating context",
  });
}

// The Rating a blind rater builds (mirrors veribayes.core.validation.human_report.Rating).
export interface RatingStepInput {
  step_id: string;
  applicable: boolean;
  status: string;
  confidence: number;
  evidence: { section_id: string; page: number | null; quote: string }[];
  rationale: string;
  applicability_reason?: string;
  missing_subtag?: string | null;
}
export interface RatingInput {
  rater_id: string;
  relationship: string;
  relevance_label: string;
  relevance_rationale: string;
  paper_class_label: string | null;
  paper_class_rationale: string;
  gate_facts: {
    inference_method: string;
    n_models: number;
    bf_claimed: boolean;
    prior_informativeness: string;
  } | null;
  steps: RatingStepInput[];
}

// Record one blind Rating. The server validates it against the contract; a 422 detail is surfaced.
export async function submitRating(paperId: string, rating: RatingInput): Promise<void> {
  await fetchJson(
    "/api/rate/submit",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paper_id: paperId, rating }),
    },
    { detail: true, error: "rating rejected" },
  );
}

// One agreement/accuracy metric (mirrors core.validation.report.Stat/RateStat). `x` is present on
// rate metrics (absence-FPR, sens/spec, …); `value` is null when uncomputable.
export interface MetricStat {
  label: string;
  value: number | null;
  n: number;
  ci_lo: number | null;
  ci_hi: number | null;
  preliminary: boolean;
  x?: number;
}

// The /api/calibration payload — either the not_yet_validated stub ({status, note}) or the full
// validation report (status ∈ {demo_fake_data, development_set, holdout}). Mirrors ValidationReport.
export interface CalibrationReport {
  status: string;
  is_demo?: boolean;
  note?: string;
  engine_version?: string;
  rubric_version?: string;
  rubric_profile?: string;
  n_papers?: number;
  n_excluded?: number;
  tier_counts?: Record<string, number>;
  rater_relationships?: Record<string, number>;
  domain_note?: string;
  validity_caveats?: string[];
  applicability_kappa?: MetricStat;
  status_kappa?: MetricStat;
  status_percent_agreement?: MetricStat;
  status_ac1?: MetricStat;
  inter_expert_status_kappa?: MetricStat;
  test_retest_kappa?: MetricStat;
  absence_fpr_strict?: MetricStat;
  absence_fpr_broad?: MetricStat;
  absence_miss_rate?: MetricStat;
  coverage_icc?: MetricStat;
  quality_icc?: MetricStat;
  relevance_sensitivity?: MetricStat;
  relevance_specificity?: MetricStat;
  paper_class_accuracy?: MetricStat;
  confusion?: Record<string, Record<string, number>>;
  tier_c_cases?: TierCCase[];
}

// A Tier-C special case — reported individually, never pooled into a rate (n too small).
export interface TierCStep {
  step_id: string;
  consensus: string;
  engine: string;
  agree: boolean;
}

export interface TierCCase {
  work_id: string;
  relevance_consensus: string;
  relevance_engine: string;
  steps: TierCStep[];
}

export async function getCalibration(): Promise<CalibrationReport> {
  return fetchJson<CalibrationReport>("/api/calibration", undefined, {
    error: "could not fetch calibration",
  });
}

export interface ProgressEvent {
  type: "status" | "stage" | "done" | "failed";
  stage?: string;
  state?: "running" | "done";
  reason?: string;
}

// Subscribe to the SSE progress stream, with a polling fallback. Returns a close() handle.
export function streamProgress(
  paperId: string,
  onEvent: (e: ProgressEvent) => void,
  onDone: () => void,
): () => void {
  let finished = false;
  let pollTimer: number | undefined;
  const es = new EventSource(`/api/papers/${paperId}/events`);

  const finish = (e: ProgressEvent) => {
    if (finished) return;
    finished = true;
    if (pollTimer) clearTimeout(pollTimer);
    es.close();
    onEvent(e);
    onDone();
  };

  // If the SSE connection drops BEFORE a terminal event (dev-server reload during the edit loop, a
  // proxy/idle timeout, tab backgrounding, a network blip), EventSource auto-reconnect is unreliable
  // across the dev proxy — so poll the job until it reaches a terminal state. The server runs the job
  // to completion regardless of whether anyone is listening, so this always resolves.
  const poll = async () => {
    if (finished) return;
    try {
      const p = await getPaper(paperId);
      if (p.status === "done" || p.status === "failed") {
        finish({ type: p.status === "failed" ? "failed" : "done" });
        return;
      }
    } catch {
      // transient (e.g. server mid-restart) — keep polling
    }
    pollTimer = window.setTimeout(poll, 1500);
  };

  es.onmessage = (msg) => {
    const e = JSON.parse(msg.data) as ProgressEvent;
    if (e.type === "done" || e.type === "failed") {
      finish(e);
      return;
    }
    onEvent(e);
  };
  es.onerror = () => {
    if (finished) return; // a normal close after the terminal event — nothing to do
    es.close(); // stop the unreliable auto-reconnect and switch to polling
    if (pollTimer === undefined) pollTimer = window.setTimeout(poll, 1500);
  };

  return () => {
    finished = true;
    if (pollTimer) clearTimeout(pollTimer);
    es.close();
  };
}
