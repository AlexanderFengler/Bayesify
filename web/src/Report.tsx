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
  Timeline,
  TimelineConnector,
  TimelineContent,
  TimelineDot,
  TimelineItem,
  timelineItemClasses,
  TimelineSeparator,
} from "@mui/lab";
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
import { MathText } from "./MathText";
import { articleUrl, formatByline } from "./paper";
import { STATUS_LABEL, STATUS_OPTIONS, useRubric, useStepNames } from "./rubric";
import type {
  AdversarialVerdict,
  AppliedCorrection,
  Evidence,
  FixItem,
  PaperState,
  ScoredResult,
  StandardRef,
  StepAssessment,
  StepStatus,
  Suggestion,
} from "./types";

// A filled status dot per severity, matching the green CheckCircle used for the "Pass" items:
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
  const titleUrl = articleUrl(paper.source_label); // link the title when submitted by URL
  const byline = formatByline(paper.paper_authors, paper.paper_year);
  const selectedStep = r.step_assessments.find((a) => a.step_id === selected) ?? null;
  const base = `/paper/${paper.paper_id}`;
  // Per-step weights (relevance of the step to this paper type) drive the weighted-mean quality;
  // join them to the assessments by step_id and surface them per card + as a header indicator.
  const weightById = new Map((r.profile?.steps ?? []).map((p) => [p.step_id, p.weight] as const));
  const anyReduced = (r.profile?.steps ?? []).some((p) => p.applicable && p.weight !== 1);
  // trusted-override corrections the override-review pass applied, joined to their steps for the
  // per-step "corrected" badge + the engine→corrected score delta.
  const corrections = paper.applied_corrections ?? [];
  const correctionByStep = new Map(corrections.map((c) => [c.step_id, c] as const));

  return (
    <>
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
          {/* the "Report" label + backend badge sit ABOVE the title/score row, so the score block's
              top aligns with the title text (not with this label row). */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
            <Typography variant="overline" color="text.secondary">
              Report
            </Typography>
            <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
          </Box>
          {/* title block and the score data on one line, 5:1 on wide screens (stacked on phones),
              tops aligned. The meta chips live BELOW this row (full width). If the paper was submitted
              by URL, the title links to it — same appearance, just clickable. */}
          <Box sx={{ display: "flex", flexDirection: { xs: "column", md: "row" }, alignItems: "flex-start", gap: 3 }}>
            <Box sx={{ flex: { md: 3 }, minWidth: 0 }}>
              <Typography variant="h4" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                {titleUrl ? (
                  <Link href={titleUrl} target="_blank" rel="noreferrer" color="inherit" underline="none">
                    <MathText>{title}</MathText>
                  </Link>
                ) : (
                  <MathText>{title}</MathText>
                )}
              </Typography>
              {byline && (
                <Typography variant="subtitle1" color="text.secondary" sx={{ mt: 0.5 }}>
                  {byline}
                </Typography>
              )}
            </Box>
            <Box sx={{ flex: { md: 1 }, minWidth: 0 }}>
              <ScoreMetrics r={r} baseQuality={paper.base_quality} nCorrections={corrections.length} />
            </Box>
          </Box>

          {/* meta chips — full width, below the title/score row (always under the numbers); persist
              across both views; hidden on the narrowest screens */}
          <Box sx={{ display: { xs: "none", sm: "flex" }, gap: 3, mt: 2, flexWrap: "wrap" }}>
            <MetaChips label="relevance" values={[r.relevance.label]} info={STAT_INFO.relevance} />
            <MetaChips label="rubric" values={[r.rubric_profile]} info={STAT_INFO.rubric} />
            {r.paper_class && (
              <MetaChips label="paper type" values={r.paper_class.labels.map((l) => l.replace(/_/g, " "))} info={STAT_INFO.paperType} />
            )}
            <MetaChips label="methods" values={METHODS} info={STAT_INFO.methods} />
            {r.profile && (
              <MetaChips label="weighting" values={[anyReduced ? "weighted" : "uniform"]} info={STAT_INFO.weighting} />
            )}
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
                    <FullReportDoc
                      steps={r.step_assessments}
                      stepNames={stepNames}
                      stepWhy={stepWhy}
                      weightById={weightById}
                      correctionByStep={correctionByStep}
                      fixList={paper.fix_list ?? []}
                      overrides={overrides}
                      onOverride={async (stepId, status, rationale, fromStatus) => {
                        await recordOverride(paper.paper_id, stepId, status, rationale, fromStatus, r.rubric_profile);
                        setOverrides((prev) => ({ ...prev, [stepId]: status }));
                      }}
                    />
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
                              weight={weightById.get(selectedStep.step_id)}
                              correction={correctionByStep.get(selectedStep.step_id)}
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
        <MathText>{r.relevance.rationale}</MathText>
      </Typography>
    </Box>
  );
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const formatLabels = (labels: string[]) => labels.map((label) => label.replace(/_/g, " ")).join(", ");

// The methods surfaced as chips in the meta row. Static for now (no per-run method detection on the
// scored result yet) — the categories the workflow recognises: MCMC, Variational, and simulation-
// based inference (SBI).
const METHODS = ["MCMC", "Variational", "SBI"];

// Hover explanations for the header stats — a one-line description plus the possible categories.
type StatInfo = { what: string; categories: string[] };
const STAT_INFO: Record<"relevance" | "rubric" | "paperType" | "methods" | "weighting", StatInfo> = {
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
  methods: {
    what: "The Bayesian computation the paper relies on.",
    categories: ["MCMC", "Variational", "SBI"],
  },
  weighting: {
    what:
      "How the Bayesify Score weights each step for this paper type. Each step carries a weight (its relevance to this paper type, 0–1, shown on its card); the score is their weighted mean over applicable steps. Multi-label papers take the max weight per step. Coverage is unweighted.",
    categories: ["weighted", "uniform"],
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

// A small all-caps label over a row of chips — the relevance / rubric / paper-type / methods row under
// the title. The chips run a size up from the report's other (small) chips so this meta row reads as
// the paper's headline facts. `info` adds a hover-explained info icon beside the label; multi-value
// fields (paper type, methods) wrap onto more chips.
function MetaChips({ label, values, info }: { label: string; values: string[]; info?: StatInfo }) {
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.75 }}>
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
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
        {values.map((v) => (
          <Chip key={v} label={cap(v)} sx={{ height: 34, fontSize: "0.9rem", fontWeight: 600, "& .MuiChip-label": { px: 1.5 } }} />
        ))}
      </Box>
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
// "Pass" check and the severity dots), in place of the status-colour legend.
function SeverityLegend() {
  const items = [
    { icon: <CheckCircleIcon sx={{ fontSize: 16, color: "success.main" }} />, label: "Pass" },
    { icon: <InfoIcon sx={{ fontSize: 16, color: "info.main" }} />, label: "Info" },
    { icon: <ErrorIcon sx={{ fontSize: 16, color: "warning.main" }} />, label: "Warning" },
    { icon: <CancelIcon sx={{ fontSize: 16, color: "error.main" }} />, label: "Omission" },
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

function ScoreMetrics({
  r,
  baseQuality,
  nCorrections = 0,
}: {
  r: ScoredResult;
  baseQuality?: number | null;
  nCorrections?: number;
}) {
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
          {nCorrections > 0 && baseQuality != null && quality != null && (
            <Typography variant="caption" sx={{ mt: 0.75, display: "block", color: "secondary.main", fontWeight: 600 }}>
              engine {Math.round(baseQuality * 100)} → {Math.round(quality * 100)} · {nCorrections}{" "}
              expert correction{nCorrections > 1 ? "s" : ""}
            </Typography>
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

// The full-report document: a left-aligned MUI Timeline, one item per step. The dot carries the step
// index tinted by its status; the connector turns dashed for a skipped (N/A) step. Each item's body
// (the "bullet points down") collapses, expanded by default. Unlike before, it is interactive — it
// shares the summary's disclosure row + Disagree control via StepBody.
function FullReportDoc({
  steps,
  stepNames,
  stepWhy,
  weightById,
  correctionByStep,
  fixList,
  overrides,
  onOverride,
}: {
  steps: StepAssessment[];
  stepNames: Record<string, string>;
  stepWhy: Record<string, string>;
  weightById: Map<string, number>;
  correctionByStep: Map<string, AppliedCorrection>;
  fixList: FixItem[];
  overrides: Record<string, StepStatus>;
  onOverride: (stepId: string, status: StepStatus, rationale: string, fromStatus: StepStatus) => Promise<void>;
}) {
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
        <Typography variant="overline" color="text.secondary">
          Full report
        </Typography>
        <SeverityLegend />
      </Box>
      {/* left-aligned, no opposite content: collapse each item's leading ::before spacer (the slot
          MUI reserves for opposite content) so the rail hugs the left and content flows right. p:0
          strips the Timeline's default symmetric padding. */}
      <Timeline
        sx={{
          p: 0,
          mt: 2,
          // Collapse each item's leading ::before spacer (MUI's opposite-content slot). Two gotchas in
          // @mui/lab v9: (1) use real CSS props (`padding`), not sx shorthands (`p`) — shorthands aren't
          // expanded inside a nested selector; (2) the default rule is now
          // `:not(:has(.MuiTimelineOppositeContent-root))::before`, whose specificity ties the plain
          // docs selector and wins on source order — so double the root class (`&&`) to outrank it.
          [`&& .${timelineItemClasses.root}::before`]: { flex: 0, padding: 0 },
        }}
      >
        {steps.map((a, i) => (
          <FullReportTimelineItem
            key={a.step_id}
            a={a}
            stepName={stepNames[a.step_id] ?? a.step_id}
            why={stepWhy[a.step_id]}
            weight={weightById.get(a.step_id)}
            correction={correctionByStep.get(a.step_id)}
            fixes={fixList.filter((f) => f.step_id === a.step_id)}
            isLast={i === steps.length - 1}
            // a skipped step dashes the connectors on BOTH sides of it: dash this item's connector
            // when this step or the next one is not-applicable.
            dashedConnector={
              a.status === "not_applicable" || steps[i + 1]?.status === "not_applicable"
            }
            overridden={overrides[a.step_id]}
            onOverride={(status, rationale) => onOverride(a.step_id, status, rationale, a.status)}
          />
        ))}
      </Timeline>
    </Box>
  );
}

// Shared diameter for the timeline dot and the title row that sits beside it — keeping them equal is
// what lets their vertical centres align on the first line.
const DOT_SIZE = 38;

function FullReportTimelineItem({
  a,
  stepName,
  why,
  weight,
  correction,
  fixes,
  isLast,
  dashedConnector,
  overridden,
  onOverride,
}: {
  a: StepAssessment;
  stepName: string;
  why?: string;
  weight?: number;
  correction?: AppliedCorrection;
  fixes: FixItem[];
  isLast: boolean;
  dashedConnector: boolean;
  overridden?: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(true); // collapsible from the bullet points down; open by default
  const na = a.status === "not_applicable";
  const meta = statusMeta(a.status);
  return (
    <TimelineItem>
      <TimelineSeparator>
        {/* the dot is the step index, tinted by status (reusing the shared status palette). Its size
            is shared with the title row (DOT_SIZE) so their vertical centres always line up. */}
        <TimelineDot
          sx={{
            m: 0,
            width: DOT_SIZE,
            height: DOT_SIZE,
            p: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "none",
            bgcolor: statusSx(meta.color),
            color: na ? "background.paper" : "common.white",
          }}
        >
          <Box component="span" sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 13, fontWeight: 700 }}>
            {a.step_id}
          </Box>
        </TimelineDot>
        {/* a skipped step dashes the connectors on both sides of it (dashedConnector); everyone else
            gets a solid one. Last item: none. */}
        {!isLast &&
          (dashedConnector ? (
            <Box sx={{ flexGrow: 1, width: 0, my: 0.5, borderLeft: "2px dashed", borderColor: "divider" }} />
          ) : (
            <TimelineConnector />
          ))}
      </TimelineSeparator>
      {/* pt:0 anchors the content's top to the dot's top; the title row is exactly DOT_SIZE tall with
          its text vertically centred, so the dot centre and the title centre coincide on the first line. */}
      <TimelineContent sx={{ pb: 4, pt: 0 }}>
        {/* header row stays visible; the chevron toggles the body below */}
        <ButtonBase
          onClick={() => setOpen((o) => !o)}
          disableRipple
          sx={{
            width: "100%",
            minHeight: DOT_SIZE,
            justifyContent: "space-between",
            alignItems: "center",
            textAlign: "left",
            gap: 1,
            borderRadius: 1,
            // no ripple/focus flash on toggle — keep the header inert-looking
            "&:hover, &.Mui-focusVisible": { bgcolor: "transparent" },
          }}
        >
          <Typography variant="h6" component="span" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
            {stepName}
          </Typography>
          <ExpandMoreIcon
            sx={{ flex: "0 0 auto", color: "text.secondary", transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }}
          />
        </ButtonBase>
        <Box sx={{ mt: 1 }}>
          <StepChips a={a} weight={weight} correction={correction} />
        </Box>
        {why && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontStyle: "italic" }}>
            <MathText>{why}</MathText>
          </Typography>
        )}
        <Collapse in={open}>
          <StepBody a={a} fixes={fixes} overridden={overridden} onOverride={onOverride} />
        </Collapse>
      </TimelineContent>
    </TimelineItem>
  );
}

// The per-step scoring weight (relevance of the step to this paper type, 0–1) that feeds the
// weighted-mean Bayesify Score. Rendered only for applicable steps (N/A steps are excluded from
// scoring); a reduced (<1) weight is drawn in amber to mark a step that counts less for this type.
function WeightChip({ weight }: { weight?: number }) {
  if (weight === undefined) return null;
  return (
    <Tooltip title="This step's weight (its relevance to this paper type, 0–1). The Bayesify Score is the weighted mean of applicable steps; coverage is unweighted.">
      <Chip
        size="small"
        variant="outlined"
        color={weight < 1 ? "warning" : "default"}
        label={`weight ${weight.toFixed(1)}`}
      />
    </Tooltip>
  );
}

// A trusted expert correction the override-review pass applied to this step: the from→to nudge, with
// a tooltip linking the source paper it was learned from, the expert's rationale, and why it applied.
function CorrectionBadge({ c }: { c: AppliedCorrection }) {
  const tip = (
    <Box sx={{ maxWidth: 320 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, display: "block" }}>
        Adjusted by a trusted expert override
      </Typography>
      <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
        Source: {c.source_paper_title || "(untitled paper)"}
        {c.override_author ? ` · ${c.override_author}` : ""}
      </Typography>
      {c.override_rationale && (
        <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
          Expert: &ldquo;{c.override_rationale}&rdquo;
        </Typography>
      )}
      {c.justification && (
        <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: "text.secondary" }}>
          Why applied: {c.justification}
        </Typography>
      )}
    </Box>
  );
  return (
    <Tooltip title={tip} arrow>
      <Chip
        size="small"
        color="secondary"
        variant="outlined"
        label={`corrected ${STATUS_LABEL[c.from_status]} → ${STATUS_LABEL[c.to_status]}`}
      />
    </Tooltip>
  );
}

// The de-carded step detail: an open section with a status-coloured left border (no card box).
function StepDetail({
  a,
  stepName,
  why,
  weight,
  correction,
  fixes,
  overridden,
  onOverride,
}: {
  a: StepAssessment;
  stepName: string;
  why?: string;
  weight?: number;
  correction?: AppliedCorrection;
  fixes: FixItem[];
  overridden?: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
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
      <Box sx={{ mt: 1 }}>
        <StepChips a={a} weight={weight} correction={correction} />
      </Box>

      {why && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontStyle: "italic" }}>
          <MathText>{why}</MathText>
        </Typography>
      )}

      <StepBody a={a} fixes={fixes} overridden={overridden} onOverride={onOverride} />
    </Box>
  );
}

// The status / confidence / weight / correction chip row — shared by the summary detail and the
// full-report timeline item so the two never drift.
function StepChips({ a, weight, correction }: { a: StepAssessment; weight?: number; correction?: AppliedCorrection }) {
  const na = a.status === "not_applicable";
  const meta = statusMeta(a.status);
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
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
      {!na && <WeightChip weight={weight} />}
      {correction && <CorrectionBadge c={correction} />}
    </Box>
  );
}

// The shared step body (the "bullet points down"): the did-well list followed by the unified
// disclosure row. An N/A step shows only its applicability reason. Used by both the summary detail
// and the full-report timeline item.
function StepBody({
  a,
  fixes,
  overridden,
  onOverride,
}: {
  a: StepAssessment;
  fixes: FixItem[];
  overridden?: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
  if (a.status === "not_applicable") {
    return (
      <Typography variant="body2" sx={{ mt: 1.5 }}>
        <MathText>{a.applicability_reason}</MathText>
      </Typography>
    );
  }
  return (
    <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
      {a.did_well.length > 0 && (
        <Box component="ul" sx={{ listStyle: "none", p: 0, m: 0, display: "flex", flexDirection: "column", gap: 0.75 }}>
          {a.did_well.map((d, i) => (
            <Box component="li" key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
              <CheckCircleIcon sx={{ fontSize: 18, color: "success.main", mt: "1px", flex: "0 0 auto" }} />
              <Typography variant="body2">
                <MathText>{d}</MathText>
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      <StepDisclosures
        suggestions={a.suggestions}
        fixes={fixes}
        evidence={a.evidence}
        standards={a.standards}
        adversarial={a.adversarial_verdict}
        currentStatus={a.status}
        overridden={overridden}
        onOverride={onOverride}
      />
    </Box>
  );
}

const SEV_RANK: Record<string, number> = { error: 0, warning: 1, info: 2 };

// Well-known reference URLs for the standards whose citation text carries no inline arXiv/DOI to
// derive a link from. Keyed by the rubric's citation id (StandardRef.source_id).
const STANDARD_URL: Record<string, string> = {
  vehtari2021: "https://arxiv.org/abs/1903.08008", // Rank-normalization… improved R-hat (Bayesian Analysis)
  vehtari2017: "https://doi.org/10.1007/s11222-016-9696-4", // Practical Bayesian model evaluation (LOO/WAIC)
  modrak2023: "https://arxiv.org/abs/2211.02383", // Simulation-based calibration checking
  betancourt_workflow: "https://betanalpha.github.io/assets/case_studies/principled_bayesian_workflow.html",
};

// A clickable URL for a standard: prefer an arXiv id or DOI embedded in the citation text (the rubric
// authors' own identifiers, so it can't be wrong), else fall back to the known-URL registry above.
function standardUrl(s: StandardRef): string | null {
  const arxiv = s.citation.match(/arXiv:\s*(\d{4}\.\d{4,5})/i);
  if (arxiv) return `https://arxiv.org/abs/${arxiv[1]}`;
  const doi = s.citation.match(/doi:\s*(10\.\S+)/i);
  if (doi) return `https://doi.org/${doi[1].replace(/[).,;]+$/, "")}`;
  return STANDARD_URL[s.source_id] ?? null;
}

// Strip a trailing internal editorial note (e.g. "[thresholds to confirm]") so the reference reads
// as a clean citation.
const cleanCitation = (c: string): string => c.replace(/\s*\[[^\]]*\]\s*$/, "");

// The per-step comment control (formerly "Disagree?", now "Add comments") is hidden for now — we'll
// revisit expert corrections later. Flip to true to bring the control (and its form) back.
const SHOW_ADD_COMMENTS = false;

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

// The unified per-step disclosure row: "Suggested fixes", "In the paper", "Standards applied" and
// "Adversarial checks" all read as sibling toggles on one line (same font), each opening its own
// panel below; the "Disagree?" control is pushed to the right of that same row (or, once an override
// is recorded, a compact note in its place). Sections with nothing to show are omitted. Fixes are
// sorted high→low by severity, with coverage impact joined from the fix-list.
function StepDisclosures({
  suggestions,
  fixes,
  evidence,
  standards,
  adversarial,
  currentStatus,
  overridden,
  onOverride,
}: {
  suggestions: Suggestion[];
  fixes: FixItem[];
  evidence: Evidence[];
  standards: StandardRef[];
  adversarial: AdversarialVerdict | null;
  currentStatus: StepStatus;
  overridden?: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
}) {
  const [showFixes, setShowFixes] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [showStandards, setShowStandards] = useState(false);
  const [showAdversarial, setShowAdversarial] = useState(false);
  const [showDisagree, setShowDisagree] = useState(false);

  const spans = evidence.filter((e) => e.kind !== "absence_search").map((e) => e.span);
  const sorted = [...suggestions].sort(
    (a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9),
  );
  const impact = new Map(fixes.map((f) => [f.text, f.coverage_delta]));
  const hasAdversarial = !!adversarial?.challenged;

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
        {suggestions.length > 0 && (
          <DisclosureToggle
            open={showFixes}
            onClick={() => setShowFixes((o) => !o)}
            // an adequate step has nothing to "fix" — its suggestions are polish, not corrections
            label={`${currentStatus === "adequate" ? "Further improvements" : "Suggested fixes"} (${suggestions.length})`}
          />
        )}
        {spans.length > 0 && (
          <DisclosureToggle open={showEvidence} onClick={() => setShowEvidence((o) => !o)} label={`In the paper (${spans.length})`} />
        )}
        {standards.length > 0 && (
          <DisclosureToggle open={showStandards} onClick={() => setShowStandards((o) => !o)} label={`Standards applied (${standards.length})`} />
        )}
        {hasAdversarial && (
          <DisclosureToggle open={showAdversarial} onClick={() => setShowAdversarial((o) => !o)} label="Refutation" />
        )}
        {/* the "Add comments" control (or its recorded-override note) sits at the right of the same
            row — hidden for now behind SHOW_ADD_COMMENTS while we rework expert corrections */}
        {SHOW_ADD_COMMENTS &&
          (overridden ? (
            <Typography variant="body2" color="text.secondary" sx={{ ml: "auto" }}>
              Override recorded: <strong>{STATUS_LABEL[overridden]}</strong>
            </Typography>
          ) : (
            <Box sx={{ ml: "auto" }}>
              <Link component="button" type="button" underline="hover" onClick={() => setShowDisagree((o) => !o)} sx={{ fontSize: "0.875rem", fontWeight: 600 }}>
                Add comments
              </Link>
            </Box>
          ))}
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
                  <MathText>{s.quote}</MathText>
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

      <Collapse in={showStandards}>
        <Box sx={{ mt: 1.5, display: "flex", flexDirection: "column", gap: 0.75 }}>
          {standards.map((s, i) => {
            const url = standardUrl(s);
            const text = cleanCitation(s.citation);
            return (
              <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                <Typography variant="body2" color="text.secondary">
                  {url ? (
                    <Link href={url} target="_blank" rel="noreferrer" underline="hover" sx={{ fontWeight: 600, color: "inherit" }}>
                      <MathText>{text}</MathText>
                    </Link>
                  ) : (
                    <MathText>{text}</MathText>
                  )}
                  {s.locator && (
                    <Box component="span" sx={{ color: "text.disabled" }}> · {s.locator}</Box>
                  )}
                </Typography>
                {s.verified ? (
                  <Chip size="small" color="success" variant="outlined" label="verified" sx={{ ml: "auto" }} />
                ) : (
                  <Chip size="small" variant="outlined" label="unverified" sx={{ ml: "auto" }} />
                )}
              </Box>
            );
          })}
        </Box>
      </Collapse>

      {hasAdversarial && (
        <Collapse in={showAdversarial}>
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              <MathText>{adversarial?.notes ?? ""}</MathText>
            </Typography>
          </Box>
        </Collapse>
      )}

      <Collapse in={SHOW_ADD_COMMENTS && showDisagree && !overridden}>
        <Box sx={{ mt: 1.5 }}>
          <DisagreeForm currentStatus={currentStatus} onOverride={onOverride} onCancel={() => setShowDisagree(false)} />
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
            <MathText>{sug.text}</MathText>
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            <MathText>{sug.how_to}</MathText>
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

// The override form (status select + optional rationale). The collapse + "Disagree?" trigger live in
// StepDisclosures; this is just the body shown when it's open.
function DisagreeForm({
  currentStatus,
  onOverride,
  onCancel,
}: {
  currentStatus: StepStatus;
  onOverride: (status: StepStatus, rationale: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [status, setStatus] = useState<StepStatus>(currentStatus);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
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
        <Button onClick={onCancel}>Cancel</Button>
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
  const titleUrl = articleUrl(paper.source_label); // link the title when submitted by URL
  const byline = formatByline(paper.paper_authors, paper.paper_year);
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
                {titleUrl ? (
                  <Link href={titleUrl} target="_blank" rel="noreferrer" color="inherit" underline="none">
                    <MathText>{paper.paper_title ?? paper.source_label}</MathText>
                  </Link>
                ) : (
                  <MathText>{paper.paper_title ?? paper.source_label}</MathText>
                )}
              </Typography>
              {byline && (
                <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {byline}
                </Typography>
              )}
              {/* The actual categorization, so the "Paper type" header has a value (not just the title) */}
              {isReview && r.paper_class && (
                <Chip
                  size="small"
                  label={formatLabels(r.paper_class.labels)}
                  sx={{ mt: 1, textTransform: "capitalize", fontWeight: 600 }}
                />
              )}
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
                <MathText>{(isReview && r.paper_class?.rationale) || r.relevance.rationale}</MathText>
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
