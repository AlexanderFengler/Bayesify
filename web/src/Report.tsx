import ArticleIcon from "@mui/icons-material/Article";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DataObjectIcon from "@mui/icons-material/DataObject";
import DownloadIcon from "@mui/icons-material/Download";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FormatQuoteIcon from "@mui/icons-material/FormatQuote";
import {
  Box,
  Button,
  ButtonBase,
  Chip,
  Collapse,
  Container,
  Divider,
  Link,
  ListItemIcon,
  Menu,
  MenuItem,
  TextField,
  Typography,
} from "@mui/material";
import { alpha, type Theme } from "@mui/material/styles";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { recordOverride } from "./api";
import { STATUS_LABEL, STATUS_OPTIONS, useRubric, useStepNames } from "./rubric";
import type {
  Evidence,
  FixItem,
  PaperState,
  ScoredResult,
  StepAssessment,
  StepStatus,
  Suggestion,
} from "./types";

// "error"-severity findings read as "omission" (a missing/incomplete workflow step) — names what's
// wrong without sounding like an accusation. The colour mapping below keeps error/warning/info hues.
const SEV_LABEL: Record<string, string> = { error: "omission", warning: "warning", info: "info" };
const sevLabel = (sev: string): string => SEV_LABEL[sev] ?? sev;
const sevColor = (sev: string): "error" | "warning" | "info" =>
  sev === "error" ? "error" : sev === "warning" ? "warning" : "info";

// One place mapping a step status onto a palette colour + label, used by the dots, pills and borders.
type PaletteKey = "success" | "warning" | "error";
function statusMeta(status: StepStatus): { color: PaletteKey | "disabled"; label: string } {
  switch (status) {
    case "adequate":
      return { color: "success", label: STATUS_LABEL.adequate };
    case "partial":
      return { color: "warning", label: STATUS_LABEL.partial };
    case "missing":
      return { color: "error", label: STATUS_LABEL.missing };
    default:
      return { color: "disabled", label: STATUS_LABEL.not_applicable };
  }
}
// resolve a status colour to a concrete CSS colour via the theme (handles the non-palette "disabled")
const statusSx = (color: PaletteKey | "disabled") =>
  color === "disabled" ? "text.disabled" : `${color}.main`;

const STRIP_LEGEND: StepStatus[] = ["adequate", "partial", "missing", "not_applicable"];
// The signifier (status) main colour, resolved from the theme — used to tint the frosted-glass cells.
function statusMainColor(t: Theme, status: StepStatus): string {
  switch (status) {
    case "adequate":
      return t.palette.success.main;
    case "partial":
      return t.palette.warning.main;
    case "missing":
      return t.palette.error.main;
    default:
      return t.palette.text.disabled;
  }
}

// The report is one full-width column with two states, driven by the URL: the summary (/paper/:id)
// and the full report (/paper/:id/full). The score data + "Steps at a glance" persist across both;
// `expanded` toggles which surrounding blocks collapse/expand, producing the slide-up morph into the
// detailed report. No tabs, no two columns.
export function Report({
  paper,
  onReset,
  onRerun,
  expanded,
}: {
  paper: PaperState;
  onReset: () => void;
  onRerun: (paperId: string) => void;
  expanded: boolean;
}) {
  const r = paper.result!;
  const navigate = useNavigate();
  // Records of expert disagreements made this session (step_id -> corrected status). Purely a UI
  // indicator; the engine output is never mutated (A5).
  const [overrides, setOverrides] = useState<Record<string, StepStatus>>({});
  // which step's detail is open on the full report; default to the first step
  const [selected, setSelected] = useState<string | null>(r.step_assessments[0]?.step_id ?? null);

  const rubric = useRubric(r.rubric_profile); // the rubric this paper was graded against
  const stepNames = useStepNames(r.rubric_profile);
  const stepWhy: Record<string, string> = Object.fromEntries(
    (rubric?.steps ?? []).flatMap((s) => (s.why ? [[s.id, s.why]] : [])),
  );

  if (r.relevance.label === "no" || r.not_applicable_reason) {
    return <NotApplicable paper={paper} onReset={onReset} onRerun={onRerun} />;
  }

  const title = paper.paper_title ?? paper.source_label;
  const selectedStep = r.step_assessments.find((a) => a.step_id === selected) ?? null;
  const base = `/paper/${paper.paper_id}`;
  const openFull = (stepId?: string) => {
    if (stepId) setSelected(stepId);
    navigate(`${base}/full`);
  };

  return (
    <>
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
          {/* back to summary — full report only, pinned at the top */}
          <Collapse in={expanded} timeout={300}>
            <Box sx={{ mb: 2 }}>
              <Link
                component="button"
                type="button"
                underline="hover"
                onClick={() => navigate(base)}
                sx={{ fontWeight: 600, fontSize: "0.875rem" }}
              >
                ← Summary
              </Link>
            </Box>
          </Collapse>

          {/* top row: the title block (left) and the score data (right), tops aligned to "REPORT" */}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 3, flexWrap: "wrap" }}>
            <Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                <Typography variant="overline" color="text.secondary">
                  Report
                </Typography>
                <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
              </Box>
              <Typography variant="h4" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                {title}
              </Typography>
              {/* chips under the title — collapse away in the full report; hidden on the narrowest screens */}
              <Collapse in={!expanded} timeout={300}>
                <Box sx={{ display: { xs: "none", sm: "flex" }, gap: 5, mt: 2, transition: "opacity 240ms", opacity: expanded ? 0 : 1 }}>
                  <Stat label="relevance" value={r.relevance.label} />
                  <Stat label="rubric" value={r.rubric_profile} />
                  {r.paper_class && (
                    <Stat label="paper type" value={r.paper_class.primary.replace(/_/g, " ")} />
                  )}
                </Box>
              </Collapse>
            </Box>
            <ScoreMetrics r={r} />
          </Box>

          <Divider sx={{ mt: 2.5 }} />

          {/* relevance gate + actions — summary only */}
          <Collapse in={!expanded} timeout={300}>
            <Box
              sx={{
                mt: 2.5,
                display: "flex",
                flexDirection: "column",
                gap: 2.5,
                transition: "opacity 240ms",
                opacity: expanded ? 0 : 1,
              }}
            >
              <RelevanceGate r={r} />
              {r.relevance.overridden && (
                <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: "warning.light", color: "text.primary", fontSize: "0.875rem" }}>
                  Graded on request. The relevance gate did not classify this as a Bayesian paper; you
                  asked for a full assessment anyway, so treat coverage and quality as provisional.
                </Box>
              )}
              <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
                <Button variant="contained" disableElevation onClick={() => openFull()}>
                  Read full report
                </Button>
                <Downloads paperId={paper.paper_id} />
                <Button variant="outlined" onClick={onReset}>
                  Analyze another
                </Button>
              </Box>
            </Box>
          </Collapse>

          {/* steps at a glance — persists; titles in the summary, none in the full report */}
          <Box sx={{ mt: { xs: 3, md: 4 } }}>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
              <Typography variant="overline" color="text.secondary">
                Steps at a glance
              </Typography>
              <Legend />
            </Box>
            <StepGlance
              steps={r.step_assessments}
              stepNames={stepNames}
              selected={expanded ? selected : null}
              showTitles={!expanded}
              onSelect={expanded ? setSelected : openFull}
            />
          </Box>

          {/* the detailed report — full report only; fades in underneath */}
          <Collapse in={expanded} timeout={300}>
            <Box sx={{ mt: 3, transition: "opacity 320ms", opacity: expanded ? 1 : 0 }}>
              {selectedStep && (
                <StepDetail
                  a={selectedStep}
                  stepName={stepNames[selectedStep.step_id] ?? selectedStep.step_id}
                  why={stepWhy[selectedStep.step_id]}
                  fixes={(paper.fix_list ?? []).filter((f) => f.step_id === selectedStep.step_id)}
                  overridden={overrides[selectedStep.step_id]}
                  onOverride={async (status, rationale) => {
                    await recordOverride(
                      paper.paper_id,
                      selectedStep.step_id,
                      status,
                      rationale,
                      selectedStep.status,
                      r.rubric_profile,
                    );
                    setOverrides((prev) => ({ ...prev, [selectedStep.step_id]: status }));
                  }}
                />
              )}
            </Box>
          </Collapse>
        </Container>
      </Box>
      <ProvenanceFooter r={r} />
    </>
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
    backend === "agent-sdk"
      ? "Claude subscription"
      : backend === "api"
        ? "Anthropic API"
        : backend === "openai"
          ? "OpenAI API"
          : backend;
  // A cache replay is labelled distinctly from a fresh live run, so a hit never masquerades as live.
  if (fromCache) {
    return <span className="backend-badge be-cache">Cached · {name}</span>;
  }
  return <span className="backend-badge be-live">Live · {name}</span>;
}

// The relevance-gate description: why the gate landed on its verdict (the value itself is in the Stat
// row above), with the gate's confidence.
function RelevanceGate({ r }: { r: ScoredResult }) {
  if (!r.relevance.rationale) return null;
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        Relevance gate · {Math.round(r.relevance.confidence * 100)}% conf.
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
        {r.relevance.rationale}
      </Typography>
    </Box>
  );
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

// A small all-caps label over a larger, slightly bolder, sentence-cased value — the relevance / rubric
// / paper-type row under the title.
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography
        sx={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "text.secondary" }}
      >
        {label}
      </Typography>
      <Typography sx={{ fontSize: "1.35rem", fontWeight: 600, lineHeight: 1.2 }}>{cap(value)}</Typography>
    </Box>
  );
}

// The status legend — sits on the "Steps at a glance" heading row, right-aligned.
function Legend() {
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5 }}>
      {STRIP_LEGEND.map((s) => (
        <Box key={s} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Box sx={{ width: 9, height: 9, borderRadius: "50%", bgcolor: statusSx(statusMeta(s).color) }} />
          <Typography variant="caption" color="text.secondary">
            {STATUS_LABEL[s]}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function ScoreMetrics({ r }: { r: ScoredResult }) {
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
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 1 }}>
      <Box sx={{ display: "flex", gap: 3 }}>
        <Box>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
            <Typography sx={{ fontSize: "2.5rem", fontWeight: 700, lineHeight: 1, color: "primary.main" }}>
              {coverageText}
            </Typography>
            {cov && (
              <Typography sx={{ color: "text.secondary", fontWeight: 600 }}>/ {cov.applicable}</Typography>
            )}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, lineHeight: 1.25 }}>
            applicable steps
            <br />
            present
          </Typography>
        </Box>
        <Box>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
            <Typography sx={{ fontSize: "2.5rem", fontWeight: 700, lineHeight: 1 }}>
              {quality == null ? "—" : Math.round(quality * 100)}
            </Typography>
            {quality != null && (
              <Typography sx={{ color: "text.secondary", fontWeight: 600 }}>/ 100</Typography>
            )}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Bayesify Score
          </Typography>
          {quality != null && (
            <Box sx={{ mt: 0.75, height: 6, borderRadius: 3, bgcolor: "action.hover", overflow: "hidden", width: 120 }}>
              <Box sx={{ height: "100%", width: `${Math.round(quality * 100)}%`, bgcolor: "primary.main" }} />
            </Box>
          )}
        </Box>
      </Box>
      {rangeNote && (
        <Typography variant="caption" color="text.secondary" sx={{ textAlign: "right" }}>
          {rangeNote}
        </Typography>
      )}
    </Box>
  );
}


function Downloads({ paperId }: { paperId: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const close = () => setAnchor(null);
  return (
    <>
      <Button
        variant="outlined"
        startIcon={<DownloadIcon />}
        endIcon={<ExpandMoreIcon />}
        onClick={(e) => setAnchor(e.currentTarget)}
      >
        Download
      </Button>
      <Menu anchorEl={anchor} open={!!anchor} onClose={close}>
        <MenuItem
          component="a"
          href={`/api/papers/${paperId}/report.json`}
          target="_blank"
          rel="noreferrer"
          onClick={close}
        >
          <ListItemIcon>
            <DataObjectIcon fontSize="small" />
          </ListItemIcon>
          report.json
        </MenuItem>
        <MenuItem
          component="a"
          href={`/api/papers/${paperId}/report.md`}
          target="_blank"
          rel="noreferrer"
          onClick={close}
        >
          <ListItemIcon>
            <ArticleIcon fontSize="small" />
          </ListItemIcon>
          report.md
        </MenuItem>
      </Menu>
    </>
  );
}

function StepGlance({
  steps,
  stepNames,
  selected,
  showTitles,
  onSelect,
}: {
  steps: StepAssessment[];
  stepNames: Record<string, string>;
  selected: string | null;
  showTitles: boolean; // summary cells carry the step title; full-report cells are compact
  onSelect: (id: string) => void;
}) {
  return (
    <Box sx={{ mt: 1.5, display: "flex", flexWrap: "nowrap", gap: 1, overflowX: "auto" }}>
      {steps.map((a) => {
        const isSel = a.step_id === selected;
        return (
          <ButtonBase
            key={a.step_id}
            onClick={() => onSelect(a.step_id)}
            focusRipple
            title={`${a.step_id} · ${stepNames[a.step_id] ?? a.step_id} — ${STATUS_LABEL[a.status]}`}
            aria-pressed={isSel}
            sx={{
              flex: "1 1 0",
              minWidth: 96,
              aspectRatio: showTitles ? "1 / 1" : "auto", // squares in the summary
              overflow: "hidden",
              flexDirection: "column",
              alignItems: "stretch",
              justifyContent: "flex-start", // override ButtonBase's default centring
              p: 1.25,
              borderRadius: 1, // less round
              // frosted-glass tile, tinted by the status colour (like the start-page panels)
              bgcolor: (t) => alpha(statusMainColor(t, a.status), 0.16),
              backdropFilter: "blur(8px)",
              border: "1px solid",
              borderColor: (t) => alpha(statusMainColor(t, a.status), 0.4),
              color: "text.primary",
              // selection (and hover) read as a ring in the status colour so the tint stays intact
              outline: "2px solid",
              outlineColor: isSel ? (t) => statusMainColor(t, a.status) : "transparent",
              transition: "outline-color 120ms",
              "&:hover": { outlineColor: isSel ? undefined : "primary.main" },
            }}
          >
            {/* top: step number, with its status indicator as a circle dot */}
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 0.75, width: "100%" }}>
              <Box component="span" sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 13, fontWeight: 700 }}>
                {a.step_id}
              </Box>
              <Box
                sx={{ width: 12, height: 12, borderRadius: "50%", flexShrink: 0, bgcolor: (t) => statusMainColor(t, a.status) }}
              />
            </Box>
            {/* a divider, then the short title — both collapse away in the full report */}
            <Box
              sx={{
                width: "100%",
                overflow: "hidden",
                maxHeight: showTitles ? 200 : 0,
                opacity: showTitles ? 1 : 0,
                transition: "max-height 300ms ease, opacity 200ms ease",
              }}
            >
              <Box sx={{ borderTop: "1px solid", borderColor: "divider", my: 1 }} />
              <Typography sx={{ fontSize: "0.78rem", fontWeight: 600, lineHeight: 1.2, textAlign: "left", color: "text.primary" }}>
                {stepNames[a.step_id] ?? a.step_id}
              </Typography>
            </Box>
          </ButtonBase>
        );
      })}
    </Box>
  );
}

// The de-carded step detail: an open section with a status-coloured left border (no card box).
function StepDetail({
  a,
  stepName,
  why,
  fixes,
  overridden,
  onOverride,
}: {
  a: StepAssessment;
  stepName: string;
  why?: string;
  fixes: FixItem[];
  overridden?: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
  const na = a.status === "not_applicable";
  const meta = statusMeta(a.status);
  return (
    <Box sx={{ pl: 2.5, borderLeft: "4px solid", borderColor: statusSx(meta.color) }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Typography component="span" sx={{ fontWeight: 700, color: "text.secondary" }}>
          {a.step_id}
        </Typography>
        <Typography variant="h6" component="span" sx={{ fontWeight: 700 }}>
          {stepName}
        </Typography>
        <Chip
          size="small"
          label={meta.label}
          sx={{
            color: na ? "text.secondary" : "common.white",
            bgcolor: na ? "action.selected" : statusSx(meta.color),
          }}
        />
        {!na && (
          <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }} title="engine confidence (uncalibrated at this milestone)">
            {Math.round(a.confidence * 100)}% conf.
          </Typography>
        )}
      </Box>

      {why && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontStyle: "italic" }}>
          {why}
        </Typography>
      )}

      {na ? (
        <Typography variant="body2" sx={{ mt: 1.5 }}>
          {a.applicability_reason}
        </Typography>
      ) : (
        <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
          {a.did_well.length > 0 && (
            <Box component="ul" sx={{ listStyle: "none", p: 0, m: 0, display: "flex", flexDirection: "column", gap: 0.75 }}>
              {a.did_well.map((d, i) => (
                <Box component="li" key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                  <CheckCircleIcon sx={{ fontSize: 18, color: "success.main", mt: "1px", flex: "0 0 auto" }} />
                  <Typography variant="body2">{d}</Typography>
                </Box>
              ))}
            </Box>
          )}

          <FixesAndEvidence suggestions={a.suggestions} fixes={fixes} evidence={a.evidence} />

          {a.standards.length > 0 && (
            <Box>
              <Typography variant="overline" color="text.secondary">
                Standard applied
              </Typography>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                {a.standards.map((s, i) => (
                  <Typography key={i} variant="body2">
                    {s.citation}
                    {s.locator && <Box component="span" sx={{ color: "text.secondary" }}> · {s.locator}</Box>}{" "}
                    <Box component="span" sx={{ color: s.verified ? "success.main" : "text.disabled", fontSize: "0.75rem" }}>
                      {s.verified ? "✓ verified" : "unverified"}
                    </Box>
                  </Typography>
                ))}
              </Box>
            </Box>
          )}

          {a.adversarial_verdict?.challenged && (
            <Typography variant="body2" color="text.secondary">
              <strong>Adversarial check</strong> {a.adversarial_verdict.notes}
            </Typography>
          )}

          {overridden ? (
            <Box sx={{ fontSize: "0.875rem", color: "text.secondary" }}>
              Expert override recorded: <strong>{STATUS_LABEL[overridden]}</strong> — recorded for the
              v1 learning loop, not yet used to change judgments.
            </Box>
          ) : (
            <DisagreeControl currentStatus={a.status} onOverride={onOverride} />
          )}
        </Box>
      )}
    </Box>
  );
}

const SEV_RANK: Record<string, number> = { error: 0, warning: 1, info: 2 };

// A disclosure toggle styled like the "See how our rubrics compare" link — one shared style so the
// "Suggested fixes" and "In the paper" toggles read identically.
function DisclosureToggle({ open, onClick, label }: { open: boolean; onClick: () => void; label: string }) {
  return (
    <Link
      component="button"
      type="button"
      underline="hover"
      onClick={onClick}
      sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, fontWeight: 600, fontSize: "0.875rem" }}
    >
      {label}
      <ExpandMoreIcon sx={{ fontSize: 18, transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
    </Link>
  );
}

// Per-step "Suggested fixes" + "In the paper" — the two toggles share one row (same font); each opens
// its own panel below. Fixes are sorted high→low by severity, with coverage impact from the fix-list.
function FixesAndEvidence({
  suggestions,
  fixes,
  evidence,
}: {
  suggestions: Suggestion[];
  fixes: FixItem[];
  evidence: Evidence[];
}) {
  const [showFixes, setShowFixes] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const spans = evidence.filter((e) => e.kind !== "absence_search").map((e) => e.span);
  const sorted = [...suggestions].sort(
    (a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9),
  );
  const impact = new Map(fixes.map((f) => [f.text, f.coverage_delta]));
  if (suggestions.length === 0 && spans.length === 0) return null;
  return (
    <Box>
      <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
        {suggestions.length > 0 && (
          <DisclosureToggle open={showFixes} onClick={() => setShowFixes((o) => !o)} label={`Suggested fixes (${suggestions.length})`} />
        )}
        {spans.length > 0 && (
          <DisclosureToggle open={showEvidence} onClick={() => setShowEvidence((o) => !o)} label={`In the paper (${spans.length})`} />
        )}
      </Box>
      <Collapse in={showFixes}>
        <Box sx={{ mt: 1.5, display: "flex", flexDirection: "column", gap: 2 }}>
          {sorted.map((sug, i) => {
            const cd = impact.get(sug.text);
            return (
              <SuggestionRow
                key={i}
                sug={sug}
                impact={cd && cd > 0 ? `fixing this lifts coverage by ${Math.round(cd * 100)} pts` : undefined}
              />
            );
          })}
        </Box>
      </Collapse>
      <Collapse in={showEvidence}>
        <Box sx={{ mt: 1.5, display: "flex", flexDirection: "column", gap: 1 }}>
          {spans.map((s, i) => (
            <Box key={i} sx={{ pl: 1.5, borderLeft: "3px solid", borderColor: "divider" }}>
              <Typography variant="body2" sx={{ display: "flex", gap: 0.5 }}>
                <FormatQuoteIcon sx={{ fontSize: 16, color: "text.disabled", flex: "0 0 auto", mt: "2px" }} />
                <span>
                  {s.quote}
                  <Box component="span" sx={{ display: "block", color: "text.secondary", fontSize: "0.75rem", mt: 0.25 }}>
                    §{s.section_id}
                    {s.page != null && `, p.${s.page}`}
                  </Box>
                </span>
              </Typography>
            </Box>
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}

function SuggestionRow({ sug, impact }: { sug: Pick<Suggestion, "severity" | "text" | "how_to" | "ease">; impact?: string }) {
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Chip size="small" color={sevColor(sug.severity)} variant="outlined" label={sevLabel(sug.severity)} />
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {sug.text}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }} title="estimated effort">
          {sug.ease} effort
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {sug.how_to}
      </Typography>
      {impact && (
        <Typography variant="caption" sx={{ color: "success.main" }}>
          {impact}
        </Typography>
      )}
    </Box>
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
      <Box>
        <Link component="button" type="button" underline="hover" onClick={() => setOpen(true)} sx={{ fontSize: "0.875rem" }}>
          Disagree?
        </Link>
      </Box>
    );
  }
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 420 }}>
      <TextField
        select
        size="small"
        label="Corrected status"
        value={status}
        onChange={(e) => setStatus(e.target.value as StepStatus)}
      >
        {STATUS_OPTIONS.map((s) => (
          <MenuItem key={s} value={s}>
            {STATUS_LABEL[s]}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        size="small"
        multiline
        minRows={2}
        placeholder="Why? (optional rationale — recorded, not used to change the judgment)"
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
      />
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button
          variant="contained"
          disableElevation
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
        </Button>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
      </Box>
    </Box>
  );
}

// ---- The not-applicable / not-Bayesian short-circuit page ---------------------------------------

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
  const isReview = r.not_applicable_reason === "not_an_application";
  return (
    <>
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="md" sx={{ py: { xs: 4, md: 6 } }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, mb: 3 }}>
            <Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                <Typography variant="overline" color="text.secondary">
                  {isReview ? "Paper type" : "Relevance gate"}
                </Typography>
                <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
              </Box>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {paper.source_label}
              </Typography>
            </Box>
            <Button variant="outlined" onClick={onReset}>
              Analyze another
            </Button>
          </Box>

          <Box sx={{ pl: 2.5, borderLeft: "4px solid", borderColor: "text.disabled" }}>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              {isReview ? "The per-step rubric doesn’t apply here" : "This doesn’t appear to apply"}
            </Typography>
            <Typography sx={{ mt: 1 }}>
              {isReview ? (
                <>
                  This reads as a review / opinion / perspective piece <em>about</em> the Bayesian
                  workflow. The per-step rubric grades papers that <strong>apply</strong> a workflow to
                  data, so it doesn&rsquo;t directly apply — <strong>nothing was graded</strong>.
                </>
              ) : (
                <>
                  The relevance gate found no Bayesian statistical methodology to assess, so no per-step
                  report was produced — <strong>nothing was graded</strong>.
                </>
              )}
            </Typography>
            <Box sx={{ mt: 2 }}>
              <Typography variant="overline" color="text.secondary">
                Why
              </Typography>
              <Typography variant="body2">
                {(isReview && r.paper_class?.rationale) || r.relevance.rationale}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {isReview && r.paper_class
                  ? `classified ${r.paper_class.primary} · ${Math.round(r.paper_class.confidence * 100)}%`
                  : `gate confidence ${Math.round(r.relevance.confidence * 100)}%`}
              </Typography>
            </Box>
            <Box sx={{ mt: 2.5 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {isReview
                  ? "If you want the per-step grade anyway, you can run it as an advisory assessment. It's recorded; coverage and quality will be marked provisional."
                  : "If you believe this is a Bayesian paper, you can override the gate and grade it anyway. The override is recorded; coverage and quality will be marked provisional."}
              </Typography>
              <Button
                variant="contained"
                disableElevation
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                  onRerun(paper.paper_id);
                }}
              >
                {busy ? "Re-running…" : "Run full assessment anyway"}
              </Button>
            </Box>
          </Box>
        </Container>
      </Box>
      <ProvenanceFooter r={r} />
    </>
  );
}

function ProvenanceFooter({ r }: { r: ScoredResult }) {
  const validated = r.validation_ref !== "unvalidated";
  return (
    <Box component="footer" sx={{ bgcolor: "background.paper", borderTop: 1, borderColor: "divider" }}>
      <Container maxWidth="lg" sx={{ py: 2 }}>
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", color: "text.secondary", fontSize: "0.8rem" }}>
          <span>engine {r.engine_version}</span>
          <span>
            rubric {r.rubric_version} · {r.rubric_profile}
          </span>
          <span>${r.cost_ledger.total_cost_usd.toFixed(3)}</span>
        </Box>
        <Typography variant="caption" color={validated ? "text.secondary" : "warning.main"}>
          {validated
            ? `development-set agreement applies (${r.validation_ref})`
            : "preliminary — the engine is not yet validated against expert ratings (validation runs at M7)."}
        </Typography>
      </Container>
    </Box>
  );
}
