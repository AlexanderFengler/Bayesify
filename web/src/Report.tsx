import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArticleIcon from "@mui/icons-material/Article";
import CancelIcon from "@mui/icons-material/Cancel";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DataObjectIcon from "@mui/icons-material/DataObject";
import DownloadIcon from "@mui/icons-material/Download";
import ErrorIcon from "@mui/icons-material/Error";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FormatQuoteIcon from "@mui/icons-material/FormatQuote";
import InfoIcon from "@mui/icons-material/Info";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
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
  Slide,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { alpha, type Theme } from "@mui/material/styles";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { SwitchTransition } from "react-transition-group";
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

// A filled status dot per severity, matching the green CheckCircle used for the "did well" items:
// a red ✕ dot for error, an amber ! dot for warning, a blue i dot for info.
function SeverityIcon({ severity }: { severity: string }) {
  const sx = { fontSize: 18, mt: "1px", flex: "0 0 auto" } as const;
  if (severity === "error") return <CancelIcon sx={{ ...sx, color: "error.main" }} />;
  if (severity === "warning") return <ErrorIcon sx={{ ...sx, color: "warning.main" }} />;
  return <InfoIcon sx={{ ...sx, color: "info.main" }} />;
}

// Confidence → a reliability colour (high = green, medium = amber, low = red). Effort → an ease
// colour (low effort is an easy win = green; high effort is costly = red). Used by the chips below.
type ChipColor = "success" | "warning" | "error";
const confidenceColor = (c: number): ChipColor => (c >= 0.8 ? "success" : c >= 0.5 ? "warning" : "error");
const EFFORT_COLOR: Record<string, ChipColor> = { low: "success", medium: "warning", high: "error" };
const effortColor = (ease: string): ChipColor => EFFORT_COLOR[ease] ?? "warning";

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
  // which step's detail is expanded inline under "Steps at a glance"; null = none open (just chips)
  const [selected, setSelected] = useState<string | null>(null);
  const toggleSelected = (id: string) => setSelected((cur) => (cur === id ? null : id));

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

  return (
    <>
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
          {/* top row: the title block (left) and the score data (right). The row stretches so the
              score block spans the left column's full height — title plus the relevance/rubric/paper-
              type row — and centres its numbers within that span rather than topping out at "REPORT". */}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "stretch", gap: 3, flexWrap: "wrap" }}>
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
              {/* chips under the title — persist across both views; hidden on the narrowest screens */}
              <Box sx={{ display: { xs: "none", sm: "flex" }, gap: 5, mt: 2 }}>
                <Stat label="relevance" value={r.relevance.label} info={STAT_INFO.relevance} />
                <Stat label="rubric" value={r.rubric_profile} info={STAT_INFO.rubric} />
                {r.paper_class && (
                  <Stat label="paper type" value={formatLabels(r.paper_class.labels)} info={STAT_INFO.paperType} />
                )}
              </Box>
            </Box>
            <ScoreMetrics r={r} />
          </Box>

          <Divider sx={{ mt: 2.5 }} />

          {/* relevance gate + actions — the gate and the summary/full toggle persist across both
              views; the override notice and the secondary actions are summary-only. */}
          <Box sx={{ mt: 2.5, display: "flex", flexDirection: "column", gap: 2.5 }}>
            <RelevanceGate r={r} />
            {r.relevance.overridden && (
              <Collapse in={!expanded} timeout={300}>
                <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: "warning.light", color: "text.primary", fontSize: "0.875rem" }}>
                  Graded on request. The relevance gate did not classify this as a Bayesian paper; you
                  asked for a full assessment anyway, so treat coverage and quality as provisional.
                </Box>
              </Collapse>
            )}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
              {/* one button, two jobs: forward into the full report, or back to the summary */}
              <Button
                variant="contained"
                disableElevation
                startIcon={expanded ? <ArrowBackIcon /> : undefined}
                endIcon={expanded ? undefined : <ArrowForwardIcon />}
                onClick={() => navigate(expanded ? base : `${base}/full`)}
              >
                {expanded ? "Back to summary" : "Read full report"}
              </Button>
              <Collapse in={!expanded} timeout={300} orientation="horizontal">
                {/* width:max-content + nowrap keep these on one line as the collapse squeezes the width */}
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, pr: 0.25, width: "max-content", whiteSpace: "nowrap" }}>
                  <Downloads paperId={paper.paper_id} />
                  <Button variant="outlined" onClick={onReset} sx={{ flexShrink: 0 }}>
                    Analyze another
                  </Button>
                </Box>
              </Collapse>
            </Box>
          </Box>

          {/* the body swipes between two views: the interactive "Steps at a glance" (click a chip to
              expand that step's detail inline) and the full-report document (every step, read-only,
              like the .md). The summary/full toggle button above drives `expanded`. */}
          <Box sx={{ mt: { xs: 3, md: 4 }, overflowX: "hidden" }}>
            <SwitchTransition mode="out-in">
              <Slide
                key={expanded ? "full" : "glance"}
                direction={expanded ? "left" : "right"}
                timeout={280}
                appear={false}
                mountOnEnter
                unmountOnExit
              >
                <Box>
                  {expanded ? (
                    <FullReportDoc steps={r.step_assessments} stepNames={stepNames} stepWhy={stepWhy} />
                  ) : (
                    <>
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
                        <Typography variant="overline" color="text.secondary">
                          Steps at a glance
                        </Typography>
                        <Legend />
                      </Box>
                      <StepGlance
                        steps={r.step_assessments}
                        stepNames={stepNames}
                        selected={selected}
                        showTitles
                        onSelect={toggleSelected}
                      />
                      <Collapse in={!!selectedStep} timeout={300}>
                        <Box sx={{ mt: 3 }}>
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
                    </>
                  )}
                </Box>
              </Slide>
            </SwitchTransition>
          </Box>
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
        Relevance gate · {Math.round(r.relevance.confidence * 100)}% Confidence
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
        {r.relevance.rationale}
      </Typography>
    </Box>
  );
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const formatLabels = (labels: string[]) => labels.map((label) => label.replace(/_/g, " ")).join(", ");

// Hover explanations for the three header stats — a one-line description plus the possible categories.
type StatInfo = { what: string; categories: string[] };
const STAT_INFO: Record<"relevance" | "rubric" | "paperType", StatInfo> = {
  relevance: {
    what: "Does the paper actually apply Bayesian statistical methodology? This gate decides whether the rubric applies.",
    categories: ["yes", "partial", "no"],
  },
  rubric: {
    what: "Which rubric the paper was graded against — the default synthesis standard or a source-pure profile.",
    categories: ["Synthesis", "Gelman (2020)", "Schad (2021)"],
  },
  paperType: {
    what: "How the paper was classified. This sets which workflow steps are applicable.",
    categories: [
      "model development",
      "method development",
      "software development",
      "data analysis",
      "numerical analysis",
      "theoretical analysis",
      "review",
    ],
  },
};

// A frosted-glass info popover (matching the app's panels): a short description, a hairline rule, then
// the categories as small chips. Shared by the three header stats.
function InfoTooltip({ info, children }: { info: StatInfo; children: React.ReactElement }) {
  return (
    <Tooltip
      arrow
      enterTouchDelay={0}
      slotProps={{
        tooltip: {
          sx: (t) => {
            // a clearly translucent frosted pane — lower alpha than the solid-ish panel glass token,
            // leaning on a strong backdrop blur to stay legible over the aurora.
            const fill = t.palette.mode === "dark" ? "rgba(40,16,72,0.42)" : "rgba(255,255,255,0.46)";
            return {
              maxWidth: 290,
              p: 0,
              bgcolor: fill,
              color: "text.primary",
              backdropFilter: "blur(18px)",
              WebkitBackdropFilter: "blur(18px)",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 2,
              boxShadow: "0 14px 36px rgba(0,0,0,0.22)",
            };
          },
        },
        arrow: {
          sx: (t) => ({ color: t.palette.mode === "dark" ? "rgba(40,16,72,0.42)" : "rgba(255,255,255,0.46)" }),
        },
      }}
      title={
        <Box sx={{ p: 1.5 }}>
          <Typography variant="body2" sx={{ color: "text.primary", lineHeight: 1.4 }}>
            {info.what}
          </Typography>
          <Divider sx={{ my: 1.25 }} />
          <Typography
            sx={{ fontSize: "0.6rem", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "text.secondary", display: "block", mb: 0.75 }}
          >
            Categories
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {info.categories.map((c) => (
              <Chip key={c} label={c} size="small" variant="outlined" sx={{ height: 22, fontSize: "0.72rem" }} />
            ))}
          </Box>
        </Box>
      }
    >
      {children}
    </Tooltip>
  );
}

// A small all-caps label over a larger, slightly bolder, sentence-cased value — the relevance / rubric
// / paper-type row under the title. `info` adds a hover-explained info icon beside the label.
function Stat({ label, value, info }: { label: string; value: string; info?: StatInfo }) {
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Typography
          sx={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "text.secondary" }}
        >
          {label}
        </Typography>
        {info && (
          <InfoTooltip info={info}>
            <InfoOutlinedIcon
              sx={{ fontSize: 15, color: "text.disabled", cursor: "help", transition: "color 120ms", "&:hover": { color: "primary.main" } }}
            />
          </InfoTooltip>
        )}
      </Box>
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

// The finding-dot legend — explains the icons used inside each step of the full report (the green
// "did well" check and the severity dots), in place of the status-colour legend.
function SeverityLegend() {
  const items = [
    { icon: <CheckCircleIcon sx={{ fontSize: 16, color: "success.main" }} />, label: "did well" },
    { icon: <InfoIcon sx={{ fontSize: 16, color: "info.main" }} />, label: "info" },
    { icon: <ErrorIcon sx={{ fontSize: 16, color: "warning.main" }} />, label: "warning" },
    { icon: <CancelIcon sx={{ fontSize: 16, color: "error.main" }} />, label: "omission" },
  ];
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5 }}>
      {items.map((it) => (
        <Box key={it.label} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          {it.icon}
          <Typography variant="caption" color="text.secondary">
            {it.label}
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
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", justifyContent: "center", gap: 1 }}>
      <Box sx={{ display: "flex", gap: { xs: 3, md: 4 } }}>
        <Box>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
            <Typography sx={{ fontSize: { xs: "2.75rem", md: "3.75rem" }, fontWeight: 700, lineHeight: 1, color: "primary.main" }}>
              {coverageText}
            </Typography>
            {cov && (
              <Typography sx={{ fontSize: "1.15rem", color: "text.secondary", fontWeight: 600 }}>/ {cov.applicable}</Typography>
            )}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, lineHeight: 1.25 }}>
            applicable steps
            <br />
            present
          </Typography>
        </Box>
        <Box>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
            <Typography sx={{ fontSize: { xs: "2.75rem", md: "3.75rem" }, fontWeight: 700, lineHeight: 1 }}>
              {quality == null ? "—" : Math.round(quality * 100)}
            </Typography>
            {quality != null && (
              <Typography sx={{ fontSize: "1.15rem", color: "text.secondary", fontWeight: 600 }}>/ 100</Typography>
            )}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, fontWeight: 700 }}>
            Bayesify Score
          </Typography>
          {quality != null && (
            <Box sx={{ mt: 1, height: 8, borderRadius: 4, bgcolor: "action.hover", overflow: "hidden", width: 160 }}>
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
  // overflowX:auto also clips the y-axis, which would shave the 2px selection/hover outline off the
  // top, bottom and outer edges of the tiles. A little padding gives the outline room; the equal
  // negative margin bleeds it back out so the tiles still align to the column edges.
  return (
    <Box
      sx={{
        mt: 1.5,
        display: "flex",
        flexWrap: "nowrap",
        gap: 1,
        overflowX: "auto",
        p: "3px",
        mx: "-3px",
      }}
    >
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
              backdropFilter: "blur(8px)",
              border: "1px solid",
              // punchcard: inactive tiles are a frosted tint of the status colour; the active tile
              // (selected, or under the pointer) is "punched" — a solid status fill with the dot and
              // labels inverted to white for the high-contrast card-flip read.
              bgcolor: (t) =>
                isSel ? statusMainColor(t, a.status) : alpha(statusMainColor(t, a.status), 0.16),
              borderColor: (t) =>
                isSel ? statusMainColor(t, a.status) : alpha(statusMainColor(t, a.status), 0.4),
              color: isSel ? "common.white" : "text.primary",
              transition: "background-color 140ms ease, border-color 140ms ease, color 140ms ease",
              "& .step-dot": {
                bgcolor: (t) => (isSel ? t.palette.common.white : statusMainColor(t, a.status)),
                transition: "background-color 140ms ease",
              },
              "& .step-rule": { borderColor: isSel ? "rgba(255,255,255,0.45)" : "divider" },
              "&:hover": {
                bgcolor: (t) => statusMainColor(t, a.status),
                borderColor: (t) => statusMainColor(t, a.status),
                color: "common.white",
              },
              "&:hover .step-dot": { bgcolor: "common.white" },
              "&:hover .step-rule": { borderColor: "rgba(255,255,255,0.45)" },
            }}
          >
            {/* top: step number, with its status indicator as a circle dot */}
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 0.75, width: "100%" }}>
              <Box component="span" sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 13, fontWeight: 700 }}>
                {a.step_id}
              </Box>
              <Box className="step-dot" sx={{ width: 12, height: 12, borderRadius: "50%", flexShrink: 0 }} />
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
              <Box className="step-rule" sx={{ borderTop: "1px solid", borderColor: "divider", my: 1 }} />
              <Typography sx={{ fontSize: "0.9rem", fontWeight: 600, lineHeight: 1.25, textAlign: "left", color: "inherit" }}>
                {stepNames[a.step_id] ?? a.step_id}
              </Typography>
            </Box>
          </ButtonBase>
        );
      })}
    </Box>
  );
}

// The full-report document: every step laid out top-to-bottom like the downloadable .md, read-only.
// It mirrors the .md content minus the unbolded suggestion bodies (how-to) and the effort chips — the
// suggestion's headline finding and its severity dot are kept. No disagree control, no disclosures.
function FullReportDoc({
  steps,
  stepNames,
  stepWhy,
}: {
  steps: StepAssessment[];
  stepNames: Record<string, string>;
  stepWhy: Record<string, string>;
}) {
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
        <Typography variant="overline" color="text.secondary">
          Full report
        </Typography>
        <SeverityLegend />
      </Box>
      <Box sx={{ mt: 2.5, display: "flex", flexDirection: "column", gap: 4 }}>
        {steps.map((a) => (
          <FullReportStep
            key={a.step_id}
            a={a}
            stepName={stepNames[a.step_id] ?? a.step_id}
            why={stepWhy[a.step_id]}
          />
        ))}
      </Box>
    </Box>
  );
}

function FullReportStep({ a, stepName, why }: { a: StepAssessment; stepName: string; why?: string }) {
  const na = a.status === "not_applicable";
  const meta = statusMeta(a.status);
  const suggestions = [...a.suggestions].sort(
    (x, y) => (SEV_RANK[x.severity] ?? 9) - (SEV_RANK[y.severity] ?? 9),
  );
  return (
    <Box sx={{ pl: 2.5, borderLeft: "4px solid", borderColor: statusSx(meta.color) }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap" }}>
        <Typography component="span" sx={{ fontWeight: 700, color: "text.secondary" }}>
          {a.step_id}
        </Typography>
        <Typography variant="h6" component="span" sx={{ fontWeight: 700 }}>
          {stepName}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1 }}>
        <Chip
          size="small"
          label={meta.label}
          sx={{
            color: na ? "text.secondary" : "common.white",
            bgcolor: na ? "action.selected" : statusSx(meta.color),
          }}
        />
        {!na && (
          <Chip
            size="small"
            variant="outlined"
            color={confidenceColor(a.confidence)}
            label={`${Math.round(a.confidence * 100)}% confidence`}
          />
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

          {suggestions.length > 0 && (
            <Box component="ul" sx={{ listStyle: "none", p: 0, m: 0, display: "flex", flexDirection: "column", gap: 0.75 }}>
              {suggestions.map((sug, i) => (
                <Box component="li" key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                  <SeverityIcon severity={sug.severity} />
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {sug.text}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}

          {a.standards.length > 0 && (
            <Box>
              <Typography variant="overline" color="text.secondary">
                Standard applied
              </Typography>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                {a.standards.map((s, i) => (
                  <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                    <Typography variant="body2">
                      {s.citation}
                      {s.locator && <Box component="span" sx={{ color: "text.secondary" }}> · {s.locator}</Box>}
                    </Typography>
                    {s.verified ? (
                      <Chip size="small" color="success" variant="outlined" label="verified" sx={{ ml: "auto" }} />
                    ) : (
                      <Chip size="small" variant="outlined" label="unverified" sx={{ ml: "auto" }} />
                    )}
                  </Box>
                ))}
              </Box>
            </Box>
          )}

          {a.adversarial_verdict?.challenged && (
            <Typography variant="body2" color="text.secondary">
              <strong>Adversarial check</strong> {a.adversarial_verdict.notes}
            </Typography>
          )}
        </Box>
      )}
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
      {/* the heading text on its own line; the status + confidence chips sit on the line below */}
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap" }}>
        <Typography component="span" sx={{ fontWeight: 700, color: "text.secondary" }}>
          {a.step_id}
        </Typography>
        <Typography variant="h6" component="span" sx={{ fontWeight: 700 }}>
          {stepName}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1 }}>
        <Chip
          size="small"
          label={meta.label}
          sx={{
            color: na ? "text.secondary" : "common.white",
            bgcolor: na ? "action.selected" : statusSx(meta.color),
          }}
        />
        {!na && (
          <Chip
            size="small"
            variant="outlined"
            color={confidenceColor(a.confidence)}
            label={`${Math.round(a.confidence * 100)}% confidence`}
            title="engine confidence (uncalibrated at this milestone)"
          />
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
              <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                {a.standards.map((s, i) => (
                  <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                    <Typography variant="body2">
                      {s.citation}
                      {s.locator && <Box component="span" sx={{ color: "text.secondary" }}> · {s.locator}</Box>}
                    </Typography>
                    {s.verified ? (
                      <Chip size="small" color="success" variant="outlined" label="verified" sx={{ ml: "auto" }} />
                    ) : (
                      <Chip size="small" variant="outlined" label="unverified" sx={{ ml: "auto" }} />
                    )}
                  </Box>
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
      {/* the effort chip sits on its own line; the severity reads as a status dot beside the text */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Chip
          size="small"
          variant="outlined"
          color={effortColor(sug.ease)}
          label={`${sug.ease} effort`}
          title="estimated effort"
        />
      </Box>
      <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", mt: 0.75 }}>
        <SeverityIcon severity={sug.severity} />
        <Box>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {sug.text}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {sug.how_to}
          </Typography>
          {impact && (
            <Typography variant="caption" sx={{ color: "success.main", display: "block", mt: 0.5 }}>
              {impact}
            </Typography>
          )}
        </Box>
      </Box>
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
                  ? `classified ${formatLabels(r.paper_class.labels)} · ${Math.round(r.paper_class.confidence * 100)}%`
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
