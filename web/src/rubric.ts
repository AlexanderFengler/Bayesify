import { useEffect, useState } from "react";
import type { StepStatus } from "./types";

// The status vocabulary — single source shared by the report view and (V3) the blind rating form, so
// the two never drift.
export const STATUS_OPTIONS: StepStatus[] = ["done_well", "partial", "missing", "not_applicable"];
export const STATUS_LABEL: Record<StepStatus, string> = {
  done_well: "done well",
  partial: "partial",
  missing: "missing",
  not_applicable: "not applicable",
};

// The compiled rubric served by GET /api/rubric — the single source of truth for step names + the
// per-step prose a rater is guided by (used in V3). Mirrors veribayes.core.rubric.models.RubricStep.
export interface RubricStepInfo {
  id: string;
  name: string;
  why: string | null; // one line: why this step matters for the workflow
  essential_for: string[];
  recommended_for: string[];
  done_well: string | null;
  done_poorly: string | null;
  citations: string[];
}
export interface Rubric {
  rubric_version: string;
  rubric_profile: string;
  label: string;
  summary: string; // the preamble: what this rubric is and its properties
  status_values: string[];
  steps: RubricStepInfo[];
}

// The rubric is static per profile; fetch once and cache (de-dupes concurrent callers).
const _cache = new Map<string, Rubric>();
const _inflight = new Map<string, Promise<Rubric>>();

export async function fetchRubric(profile = "synthesis"): Promise<Rubric> {
  const hit = _cache.get(profile);
  if (hit) return hit;
  let p = _inflight.get(profile);
  if (!p) {
    p = fetch(`/api/rubric?profile=${encodeURIComponent(profile)}`)
      .then((r) => {
        if (!r.ok) throw new Error("could not fetch rubric");
        return r.json() as Promise<Rubric>;
      })
      .then((r) => {
        _cache.set(profile, r);
        return r;
      });
    _inflight.set(profile, p);
  }
  return p;
}

// The full rubric for a profile (cached). null until loaded — used for the report preamble.
export function useRubric(profile = "synthesis"): Rubric | null {
  const [rubric, setRubric] = useState<Rubric | null>(() => _cache.get(profile) ?? null);
  useEffect(() => {
    let alive = true;
    fetchRubric(profile)
      .then((r) => {
        if (alive) setRubric(r);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [profile]);
  return rubric;
}

// Step-id -> display name, from the rubric (replaces the hardcoded map that could drift from the
// rubric files). Empty until loaded; the engine step_id is the fallback.
export function useStepNames(profile = "synthesis"): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>(() => {
    const c = _cache.get(profile);
    return c ? Object.fromEntries(c.steps.map((s) => [s.id, s.name])) : {};
  });
  useEffect(() => {
    let alive = true;
    fetchRubric(profile)
      .then((r) => {
        if (alive) setNames(Object.fromEntries(r.steps.map((s) => [s.id, s.name])));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [profile]);
  return names;
}
