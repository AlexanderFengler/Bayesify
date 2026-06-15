import type { Rubric } from "./rubric";
import type { PaperState } from "./types";

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
  const res = await fetch("/api/papers", { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "upload failed");
  }
  const body = await res.json();
  return body.paper_id as string;
}

export async function getPaper(paperId: string): Promise<PaperState> {
  const res = await fetch(`/api/papers/${paperId}`);
  if (!res.ok) throw new Error("could not fetch paper");
  return (await res.json()) as PaperState;
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
  const res = await fetch(`/api/assessments/${paperId}/steps/${stepId}/override`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("could not record override");
}

// Re-run a short-circuited paper as 'partial' (the gate-page escape hatch). Returns the paper_id.
export async function rerun(paperId: string): Promise<string> {
  const form = new FormData();
  form.set("relevance_override", "partial");
  const res = await fetch(`/api/papers/${paperId}/rerun`, { method: "POST", body: form });
  if (!res.ok) throw new Error("could not re-run");
  return (await res.json()).paper_id as string;
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
  const res = await fetch(`/api/rate/context/${paperId}`);
  if (!res.ok) throw new Error("could not load rating context");
  return (await res.json()) as RateContext;
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
  const res = await fetch("/api/rate/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId, rating }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : "rating rejected");
  }
}

export interface Calibration {
  status: string; // "not_yet_validated" until the M7 validation run produces agreement metrics
  note: string;
  agreement?: Record<string, number> | null; // populated post-M7; absent/empty for now
}

// Fetch the engine's calibration status. Honest by construction: pre-M7 it reports
// "not_yet_validated" with no agreement metrics (the validation run hasn't happened yet).
export async function getCalibration(): Promise<Calibration> {
  const res = await fetch("/api/calibration");
  if (!res.ok) throw new Error("could not fetch calibration");
  return (await res.json()) as Calibration;
}

export interface ProgressEvent {
  type: "status" | "stage" | "done" | "failed";
  stage?: string;
  state?: "running" | "done";
  reason?: string;
}

// Subscribe to the SSE progress stream. Returns a close() handle.
export function streamProgress(
  paperId: string,
  onEvent: (e: ProgressEvent) => void,
  onDone: () => void,
): () => void {
  const es = new EventSource(`/api/papers/${paperId}/events`);
  es.onmessage = (msg) => {
    const e = JSON.parse(msg.data) as ProgressEvent;
    onEvent(e);
    if (e.type === "done" || e.type === "failed") {
      es.close();
      onDone();
    }
  };
  es.onerror = () => {
    // The stream closes itself on terminal events; an error after that is expected. If it errors
    // before completion the polling fallback in App will still resolve the result.
    es.close();
  };
  return () => es.close();
}
