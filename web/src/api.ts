import type { Rubric } from "./rubric";
import type { ArchiveFilters, ArchiveResponse, PaperState } from "./types";

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
  profile?: string; // which rubric to grade against (registry id; default synthesis)
}

export interface SubmitResult {
  paperId: string;
  archiveHit: boolean;
  sessionHit: boolean;
}

// One available rubric, for the pickers (GET /api/rubrics).
export interface RubricSummary {
  id: string;
  label: string;
  summary: string;
  rubric_version: string;
}

export async function fetchRubrics(): Promise<RubricSummary[]> {
  return fetchJson<RubricSummary[]>("/api/rubrics", undefined, { error: "could not load rubrics" });
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

export async function submitPaper(input: SubmitInput): Promise<SubmitResult> {
  const form = new FormData();
  form.set("mode", input.mode);
  form.set("profile", input.profile || "synthesis");
  if (input.file) form.set("file", input.file);
  else if (input.identifier) {
    for (const [k, val] of Object.entries(classifyIdentifier(input.identifier))) form.set(k, val);
  }
  const body = await fetchJson<{
    paper_id: string;
    archive_hit?: boolean;
    session_hit?: boolean;
  }>(
    "/api/papers",
    { method: "POST", body: form },
    { detail: true, error: "upload failed" },
  );
  return {
    paperId: body.paper_id,
    archiveHit: body.archive_hit === true,
    sessionHit: body.session_hit === true,
  };
}

export async function getPaper(paperId: string): Promise<PaperState> {
  return fetchJson<PaperState>(`/api/papers/${paperId}`, undefined, { error: "could not fetch paper" });
}

// A trusted reviewer's shared-secret token (matched against BAYESIFY_TRUSTED_TOKENS on the server).
// Stored locally; when present, a recorded disagreement is promoted to a trusted correction that
// adjusts the grade. Absent → the disagreement is advisory only.
const REVIEWER_TOKEN_KEY = "bayesify.reviewerToken";
export function getReviewerToken(): string {
  try {
    return localStorage.getItem(REVIEWER_TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}
export function setReviewerToken(token: string): void {
  try {
    if (token) localStorage.setItem(REVIEWER_TOKEN_KEY, token);
    else localStorage.removeItem(REVIEWER_TOKEN_KEY);
  } catch {
    /* localStorage unavailable (e.g. private mode) — the token just won't persist */
  }
}

export interface OverrideResult {
  recorded: boolean;
  trusted: boolean; // true when a valid reviewer token promoted this to a trusted correction
}

// Record an expert disagreement on one step. A trusted reviewer token promotes it to a correction
// that adjusts the grade; otherwise it is recorded as an advisory note. Never mutates engine output.
export async function recordOverride(
  paperId: string,
  stepId: string,
  correctedStatus: string,
  rationale: string,
  originalStatus?: string, // the engine verdict being disagreed with (what was overridden)
  rubricProfile?: string, // which rubric this report was graded under
): Promise<OverrideResult> {
  const form = new FormData();
  form.set("corrected_status", correctedStatus);
  form.set("rationale", rationale);
  form.set("author", "you");
  if (originalStatus) form.set("original_status", originalStatus);
  if (rubricProfile) form.set("rubric_profile", rubricProfile);
  const token = getReviewerToken();
  if (token) form.set("token", token);
  return await fetchJson<OverrideResult>(
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
  version_label: string | null;
  rubric: Rubric;
  evidence: RateContextSpan[];
  where_looked: { section_id: string; title: string; kind: string; page: number | null }[];
}

// Load the BLIND rating context (rubric + detector evidence only — never the engine's ScoredResult).
export async function fetchRateContext(
  paperId: string,
  profile = "synthesis",
): Promise<RateContext> {
  return fetchJson<RateContext>(
    `/api/rate/context/${paperId}?profile=${encodeURIComponent(profile)}`,
    undefined,
    { error: "could not load rating context" },
  );
}

// The Rating a blind rater builds (mirrors bayesify.core.validation.human_report.Rating).
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
  paper_class_labels: string[];
  paper_class_rationale: string;
  gate_facts: {
    inference_method: string;
    n_models: number;
    bf_claimed: boolean;
    prior_informativeness: string;
  } | null;
  steps: RatingStepInput[];
  tags: string[]; // freeform tags the rater attaches (the Archive's manual tags)
}

// Record one blind Rating. The server validates it against the contract; a 422 detail is surfaced.
// `provenance` (the sha/version from rate/context) is echoed back so the server can still pin the
// gold record if the in-memory job has expired — otherwise an hour-long blind pass would be lost.
export async function submitRating(
  paperId: string,
  rating: RatingInput,
  profile = "synthesis",
  provenance: { source_sha256?: string | null; version_label?: string | null } = {},
): Promise<void> {
  await fetchJson(
    "/api/rate/submit",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paper_id: paperId,
        profile,
        rating,
        source_sha256: provenance.source_sha256 ?? "",
        version_label: provenance.version_label ?? "",
      }),
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

// --- About-us contact form ------------------------------------------------------------------------

export interface ContactInput {
  name: string;
  email: string;
  message: string;
}

// Relay a visitor's message to the team via the backend (which sends it through Resend). Surfaces
// the API's {detail} on failure (e.g. 503 when the form is not configured) so the UI can show it.
export async function sendContact(input: ContactInput): Promise<void> {
  await fetchJson(
    "/api/contact",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    { detail: true, error: "could not send your message" },
  );
}

export async function getCalibration(): Promise<CalibrationReport> {
  return fetchJson<CalibrationReport>("/api/calibration", undefined, {
    error: "could not fetch calibration",
  });
}

// --- Archive (processed papers + tag search) ------------------------------------------------------

// Fetch the archive (from the shared Mongo reports store), optionally filtered. Free text (`q`)
// matches title/authors; auto-tag arrays filter server-side (OR within a facet, AND across facets).
// `facets` are the full-archive
// tag vocabularies for the filter chips.
export async function fetchPapers(filters: ArchiveFilters = {}): Promise<ArchiveResponse> {
  const p = new URLSearchParams();
  if (filters.q) p.set("q", filters.q);
  for (const v of filters.paper_type ?? []) p.append("paper_type", v);
  for (const v of filters.discipline ?? []) p.append("discipline", v);
  for (const v of filters.method ?? []) p.append("method", v);
  for (const v of filters.software ?? []) p.append("software", v);
  if (filters.mode) p.set("mode", filters.mode);
  if (filters.rubric) p.set("rubric", filters.rubric);
  const qs = p.toString();
  return fetchJson<ArchiveResponse>(`/api/papers${qs ? `?${qs}` : ""}`, undefined, {
    error: "could not load the archive",
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
    let e: ProgressEvent;
    try {
      e = JSON.parse(msg.data) as ProgressEvent;
    } catch {
      // a malformed frame (proxy noise, truncation) — skip it rather than let the throw kill the
      // handler. If the *terminal* frame is the mangled one, the polling fallback still resolves:
      // the connection's eventual close fires onerror, which switches to polling.
      return;
    }
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
