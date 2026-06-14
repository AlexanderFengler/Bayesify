// TypeScript mirror of the fields of veribayes.core.schema.ScoredResult that the report renders.
// The contract is owned by core/schema.py (§4.3); this is the read-side view.

export type StepStatus = "done_well" | "partial" | "missing" | "not_applicable";
export type Severity = "error" | "warning" | "info";
export type Ease = "low" | "medium" | "high";

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
export interface Relevance {
  label: "yes" | "partial" | "no";
  confidence: number;
  rationale: string;
}
export interface PaperClass {
  primary: string;
  secondary: string | null;
  confidence: number;
  rationale: string;
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
  coverage: Coverage | null;
  quality_score: number | null;
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

export interface PaperState {
  paper_id: string;
  status: "queued" | "running" | "done" | "failed";
  stage: string | null;
  mode: string;
  source_label: string;
  result: ScoredResult | null;
  inventory: EvidenceInventory | null;
  parser: string | null;
  parser_version: string | null;
  backend: string | null; // "agent-sdk" | "api" | "stub" — who produced the result
  from_cache: boolean; // true if this was a cached replay, not a fresh run
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
// Local-only mode runs detectors only — no LLM, no scores.
export const LOCAL_STAGES = ["ingest", "parse", "detect"] as const;
export type Stage = (typeof STAGES)[number];
