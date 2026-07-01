// TypeScript mirror of the fields of bayesify.core.schema.ScoredResult that the report renders.
// The contract is owned by core/schema.py (Â§4.3); this is the read-side view.

export type StepStatus = "adequate" | "partial" | "missing" | "not_applicable";
export type Severity = "error" | "warning" | "info";
export type Ease = "low" | "medium" | "high";
export type ExpectationTier = "expected" | "recommended" | "none";

export interface EvidenceSpan {
  section_id: string;
  page: number | null;
  quote: string;
}
export interface Evidence {
  detector_id: string;
  detector_version: string;
  kind: string;
  value: Record<string, unknown> | null;
  span: EvidenceSpan;
}
export interface StandardRef {
  source_id: string;
  citation: string;
  verified: boolean;
  locator: string | null;
}
export interface Suggestion {
  severity: Severity;
  text: string;
  how_to: string;
  ease: Ease;
}
export interface AdversarialVerdict {
  challenged: boolean;
  refuted: boolean;
  notes: string;
}
export interface StepAssessment {
  step_id: string;
  applicable: boolean;
  applicability_reason: string;
  status: StepStatus;
  confidence: number;
  evidence: Evidence[];
  standards: StandardRef[];
  did_well: string[];
  suggestions: Suggestion[];
  adversarial_verdict: AdversarialVerdict | null;
}
export interface Coverage {
  present: number;
  applicable: number;
  strict: number;
  lenient: number;
}
// Per-step scoring profile: the weight (relevance of the step to this paper type, in [0,1]) that
// feeds the weighted-mean quality, plus the expectation tier. Joined to StepAssessment by step_id.
export interface StepProfile {
  step_id: string;
  applicable: boolean;
  status: StepStatus;
  sub_score: number | null;
  weight: number;
  tier: ExpectationTier;
}
export interface Profile {
  steps: StepProfile[];
  n_applicable: number;
  n_na: number;
  n_uncertain: number;
}
// One trusted expert correction the override-review pass applied to a step, with the link back to
// the source paper it was learned from (shown in a tooltip) and how much it moved the scores.
export interface AppliedCorrection {
  step_id: string;
  from_status: StepStatus;
  to_status: StepStatus;
  coverage_delta: number;
  quality_delta: number;
  override_author: string;
  override_rationale: string;
  source_paper_title: string;
  justification: string;
}
export interface Relevance {
  label: "yes" | "partial" | "no";
  confidence: number;
  rationale: string;
  overridden: boolean; // true when a human overrode the gate (the rerun escape hatch)
}
export interface PaperClass {
  labels: string[];
  disciplines: string[]; // soft-vocabulary scientific fields (multi-label); drives the Archive facet
  confidence: number;
  rationale: string;
}

// --- Archive: one processed paper + its tags (mirror of bayesify.api.papers_store.ArchivedPaper) ---
export interface ArchivePaper {
  key: string; // durable archive id (also the tag-edit path segment)
  paper_id: string;
  source_sha256: string;
  rubric_profile: string;
  version_label: string;
  source_label: string;
  paper_title: string | null;
  paper_authors: string[];
  paper_year: number | null;
  mode: string; // "full" (AI) | "local" (Human)
  backend: string | null;
  relevance_label: string;
  quality_score: number | null;
  coverage_present: number | null;
  coverage_applicable: number | null;
  paper_type: string[]; // auto
  discipline: string[]; // auto
  methods: string[]; // auto
  manual_tags: string[]; // freeform, human-editable
  created_at: string;
  updated_at: string;
}
export interface ArchiveFacets {
  paper_type: string[];
  discipline: string[];
  methods: string[];
  tags: string[];
}
export interface ArchiveResponse {
  papers: ArchivePaper[];
  facets: ArchiveFacets;
  total: number;
}
export interface ArchiveFilters {
  q?: string;
  paper_type?: string[];
  discipline?: string[];
  method?: string[];
  tag?: string[];
  mode?: string;
  rubric?: string;
}
export interface CostLedger {
  entries: { stage: string; model: string; input_tokens: number; output_tokens: number; cost_usd: number }[];
  total_tokens: number;
  total_cost_usd: number;
}
export interface ScoredResult {
  relevance: Relevance;
  paper_class: PaperClass | null;
  step_assessments: StepAssessment[];
  profile: Profile | null; // per-step weights + tiers (drives the weighted-mean quality)
  coverage: Coverage | null;
  quality_score: number | null;
  not_applicable_reason: string | null; // "not_bayesian" | "not_an_application" when not graded
  engine_version: string;
  rubric_version: string;
  rubric_profile: string;
  cost_ledger: CostLedger;
  validation_ref: string;
}

// --- Local-only detection inventory (mirror of core/detectors EvidenceInventory) ---
export interface InventoryHit {
  detector_id: string;
  family: string;
  kind: string;
  value: Record<string, unknown> | null;
  section_id: string;
  section_title: string;
  page: number | null;
  quote: string;
}
export interface InventoryFamily {
  family: string;
  found: InventoryHit[];
  not_detected: string[];
}
export interface ScannedSection {
  section_id: string;
  kind: string;
  title: string;
  page: number | null;
}
export interface EvidenceInventory {
  families: InventoryFamily[];
  where_looked: ScannedSection[];
  skipped: ScannedSection[];
  n_hits: number;
}

export interface FixItem {
  step_id: string;
  severity: Severity;
  text: string;
  how_to: string;
  ease: Ease;
  weight: number;
  coverage_delta: number;
  quality_delta: number;
}

export interface PaperState {
  paper_id: string;
  status: "queued" | "running" | "done" | "failed";
  stage: string | null;
  mode: string;
  source_label: string;
  paper_title: string | null; // best-effort title from parsing; falls back to source_label for display
  paper_authors: string[]; // best-effort author names (provider or PDF metadata); may be empty
  paper_year: number | null; // best-effort publication year (provider or PDF metadata); may be null

  relevance_override: string | null; // set when the user forced a short-circuited paper to be graded
  result: ScoredResult | null;
  fix_list: FixItem[] | null;
  inventory: EvidenceInventory | null;
  parser: string | null;
  parser_version: string | null;
  backend: string | null; // "agent-sdk" | "api" | "openai" | "stub" - who produced the result
  from_cache: boolean; // true if this was a cached replay, not a fresh run
  // override-review provenance: trusted corrections overlaid on `result` + the pre-overlay engine
  // coverage/quality, so the report can show what changed and link the source paper.
  applied_corrections: AppliedCorrection[];
  base_coverage: Coverage | null;
  base_quality: number | null;
  local_notice: string | null;
  error: string | null;
}

export const STAGES = [
  "ingest",
  "parse",
  "detect",
  "screen",
  "classify",
  "assess",
  "score",
] as const;
// Local-only mode runs detectors only no LLM, no scores.
export const LOCAL_STAGES = ["ingest", "parse", "detect"] as const;
export type Stage = (typeof STAGES)[number];

