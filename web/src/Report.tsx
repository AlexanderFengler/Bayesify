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
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
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
    case "done_well":
      return { color: "success", label: STATUS_LABEL.done_well };
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

// The at-a-glance cells are colour-coded across the whole cell (soft status fill + status text), the
// way the original strip was. `.light` palette slots are the *-soft tokens; NA uses a neutral grey.
const STATUS_GLYPH: Record<StepStatus, string> = {
  done_well: "✓",
  partial: "◐",
  missing: "✗",
  not_applicable: "–",
};
const STRIP_LEGEND: StepStatus[] = ["done_well", "partial", "missing", "not_applicable"];
function cellColors(status: StepStatus): { bg: string; fg: string } {
  switch (status) {
    case "done_well":
      return { bg: "success.light", fg: "success.main" };
    case "partial":
      return { bg: "warning.light", fg: "warning.main" };
    case "missing":
      return { bg: "error.light", fg: "error.main" };
    default:
      return { bg: "action.hover", fg: "text.disabled" };
  }
}

export function Report({
  paper,
  onReset,
  onRerun,
}: {
  paper: PaperState;
  onReset: () => void;
  onRerun: (paperId: string) => void;
}) {
  const r = paper.result!;
  // Records of expert disagreements made this session (step_id -> corrected status). Purely a UI
  // indicator; the engine output is never mutated (A5).
  const [overrides, setOverrides] = useState<Record<string, StepStatus>>({});
  const [tab, setTab] = useState<"report" | "fixes">("report");
  // which step's detail is open in the right column; default to the first step
  const [selected, setSelected] = useState<string | null>(r.step_assessments[0]?.step_id ?? null);

  const rubric = useRubric(r.rubric_profile); // the rubric this paper was graded against
  const stepNames = useStepNames(r.rubric_profile);
  const stepWhy: Record<string, string> = Object.fromEntries(
    (rubric?.steps ?? []).flatMap((s) => (s.why ? [[s.id, s.why]] : [])),
  );

  if (r.relevance.label === "no" || r.not_applicable_reason) {
    return <NotApplicable paper={paper} onReset={onReset} onRerun={onRerun} />;
  }

  const selectedStep = r.step_assessments.find((a) => a.step_id === selected) ?? null;

  return (
    <>
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="lg" sx={{ py: { xs: 3, md: 5 } }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
            <Tab value="report" label="Report" />
            <Tab value="fixes" label="Priority fixes" />
          </Tabs>

          {tab === "report" ? (
            <Box
              sx={{
                display: "flex",
                flexDirection: { xs: "column", md: "row" },
                gap: { xs: 4, md: 6 },
                alignItems: "flex-start",
              }}
            >
              {/* LEFT: everything above "steps at a glance" + the relevance gate */}
              <Box sx={{ flex: { md: "0 0 38%" }, width: "100%", position: { md: "sticky" }, top: { md: 24 } }}>
                <SummaryColumn paper={paper} r={r} onReset={onReset} />
              </Box>

              {/* RIGHT: steps at a glance (buttons) + the selected step's de-carded detail */}
              <Box sx={{ flex: "1 1 0", width: "100%", minWidth: 0 }}>
                <Typography variant="overline" color="text.secondary">
                  Steps at a glance
                </Typography>
                <StepGlance
                  steps={r.step_assessments}
                  stepNames={stepNames}
                  selected={selected}
                  onSelect={setSelected}
                />
                {selectedStep && (
                  <Box sx={{ mt: 3 }}>
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
                  </Box>
                )}
              </Box>
            </Box>
          ) : (
            <FixesPage r={r} fixes={paper.fix_list} />
          )}
        </Container>
      </Box>
      <ProvenanceFooter r={r} />
    </>
  );
}

// ---- LEFT column ---------------------------------------------------------------------------------

function SummaryColumn({
  paper,
  r,
  onReset,
}: {
  paper: PaperState;
  r: ScoredResult;
  onReset: () => void;
}) {
  const title = paper.paper_title ?? paper.source_label;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
      <Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
          <Typography variant="overline" color="text.secondary">
            Report
          </Typography>
          <BackendBadge backend={paper.backend} fromCache={paper.from_cache} />
        </Box>
        <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.25 }}>
          {title}
        </Typography>

        {/* relevance · rubric · paper type — small all-caps labels over larger values, one line */}
        <Box sx={{ display: "flex", gap: 4, flexWrap: "wrap", mt: 2 }}>
          <Stat label="relevance" value={r.relevance.label} />
          <Stat label="rubric" value={r.rubric_profile} />
          {r.paper_class && <Stat label="paper type" value={r.paper_class.primary.replace(/_/g, " ")} />}
        </Box>
      </Box>

      <Divider />

      <ScoreMetrics r={r} />

      {r.relevance.overridden && (
        <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: "warning.light", color: "text.primary", fontSize: "0.875rem" }}>
          Graded on request. The relevance gate did not classify this as a Bayesian paper; you asked
          for a full assessment anyway, so treat coverage and quality as provisional.
        </Box>
      )}

      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Downloads paperId={paper.paper_id} />
        <Button size="small" variant="outlined" onClick={onReset}>
          Analyze another
        </Button>
      </Box>
    </Box>
  );
}

// A small all-caps label over a larger, slightly bolder value — the relevance/rubric/paper-type row.
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography
        sx={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "text.secondary" }}
      >
        {label}
      </Typography>
      <Typography sx={{ fontSize: "1.05rem", fontWeight: 600, lineHeight: 1.3 }}>{value}</Typography>
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
  const total = r.step_assessments.length;
  const naCount = cov ? total - cov.applicable : 0;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
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
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            applicable steps present
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
            quality score
          </Typography>
          {quality != null && (
            <Box sx={{ mt: 0.75, height: 6, borderRadius: 3, bgcolor: "action.hover", overflow: "hidden", width: 120 }}>
              <Box sx={{ height: "100%", width: `${Math.round(quality * 100)}%`, bgcolor: "primary.main" }} />
            </Box>
          )}
        </Box>
      </Box>
      {(naCount > 0 || rangeNote) && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
          {cov && naCount > 0 && (
            <Typography variant="caption" color="text.secondary">
              {naCount} of {total} steps not applicable (excluded from the denominator)
            </Typography>
          )}
          {rangeNote && (
            <Typography variant="caption" color="text.secondary">
              {rangeNote}
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}

function BackendBadge({ backend, fromCache }: { backend: string | null; fromCache: boolean }) {
  if (!backend) return null;
  if (backend === "stub") {
    return <Chip size="small" variant="outlined" color="warning" label="Stub engine · no model" />;
  }
  const name =
    backend === "agent-sdk" ? "Claude subscription" : backend === "api" ? "Anthropic API" : backend;
  return (
    <Chip
      size="small"
      variant="outlined"
      color={fromCache ? "default" : "success"}
      label={`${fromCache ? "Cached" : "Live"} · ${name}`}
    />
  );
}

function Downloads({ paperId }: { paperId: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const close = () => setAnchor(null);
  return (
    <>
      <Button
        size="small"
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

// ---- RIGHT column: the at-a-glance buttons + selected step detail --------------------------------

function StepGlance({
  steps,
  stepNames,
  selected,
  onSelect,
}: {
  steps: StepAssessment[];
  stepNames: Record<string, string>;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Box sx={{ mt: 1 }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {steps.map((a) => {
          const isSel = a.step_id === selected;
          const c = cellColors(a.status);
          return (
            <ButtonBase
              key={a.step_id}
              onClick={() => onSelect(a.step_id)}
              focusRipple
              title={`${a.step_id} · ${stepNames[a.step_id] ?? a.step_id} — ${STATUS_LABEL[a.status]}`}
              aria-pressed={isSel}
              sx={{
                flex: "1 1 0",
                minWidth: 56,
                flexDirection: "column",
                gap: "3px",
                py: 1,
                px: 0.5,
                borderRadius: 2,
                bgcolor: c.bg,
                color: c.fg,
                // selection (and hover) read as a ring so the status colour stays intact
                outline: "2px solid",
                outlineColor: isSel ? "currentColor" : "transparent",
                transition: "outline-color 120ms",
                "&:hover": { outlineColor: isSel ? "currentColor" : "primary.light" },
              }}
            >
              <Box component="span" sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 12, fontWeight: 700 }}>
                {a.step_id}
              </Box>
              <Box component="span" sx={{ fontSize: 14, lineHeight: 1 }}>
                {STATUS_GLYPH[a.status]}
              </Box>
            </ButtonBase>
          );
        })}
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 1.5 }}>
        {STRIP_LEGEND.map((s) => (
          <Box key={s} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: statusSx(statusMeta(s).color) }} />
            <Typography variant="caption" color="text.secondary">
              {STATUS_LABEL[s]}
            </Typography>
          </Box>
        ))}
      </Box>
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

          {a.suggestions.map((sug, i) => (
            <SuggestionRow key={i} sug={sug} />
          ))}

          {fixes.length > 0 && (
            <Box>
              <Typography variant="overline" color="text.secondary">
                Suggested fixes
              </Typography>
              {fixes.map((f, i) => (
                <Box key={i} sx={{ mt: 0.5 }}>
                  <SuggestionRow
                    sug={{ severity: f.severity, text: f.text, how_to: f.how_to, ease: f.ease }}
                    impact={
                      f.coverage_delta > 0
                        ? `fixing this lifts coverage by ${(f.coverage_delta * 100).toFixed(0)} pts`
                        : undefined
                    }
                  />
                </Box>
              ))}
            </Box>
          )}

          <EvidencePanel evidence={a.evidence} />

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

// "In the paper" — collapsible verbatim evidence spans. Replaces the CSS <details> with MUI Collapse.
function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  const spans = evidence.filter((e) => e.kind !== "absence_search").map((e) => e.span);
  const [open, setOpen] = useState(false);
  if (spans.length === 0) return null;
  return (
    <Box>
      <Link
        component="button"
        type="button"
        underline="hover"
        color="text.secondary"
        onClick={() => setOpen((o) => !o)}
        sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, fontSize: "0.8rem", fontWeight: 600 }}
      >
        In the paper ({spans.length})
        <ExpandMoreIcon sx={{ fontSize: 18, transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
      </Link>
      <Collapse in={open}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
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

// ---- Page 2: ranked cross-step priority fixes ---------------------------------------------------

function FixesPage({ r, fixes }: { r: ScoredResult; fixes: FixItem[] | null }) {
  const cov = r.coverage;
  const needsAttention = r.step_assessments.filter(
    (a) => a.status === "missing" || a.status === "partial",
  ).length;
  return (
    <Box sx={{ maxWidth: 760 }}>
      <Typography variant="overline" color="text.secondary">
        Summary
      </Typography>
      <Typography sx={{ mb: 3 }}>
        {cov ? (
          <>
            <strong>
              {cov.present} of {cov.applicable}
            </strong>{" "}
            applicable steps present
            {r.quality_score != null && (
              <>
                {" · quality "}
                <strong>{r.quality_score.toFixed(2)}</strong>
              </>
            )}
            {needsAttention > 0 ? (
              <>
                {" · "}
                <strong>{needsAttention}</strong> step{needsAttention === 1 ? "" : "s"} to improve.
              </>
            ) : (
              " · nothing flagged."
            )}
          </>
        ) : (
          "No applicable steps to summarize."
        )}
      </Typography>

      {!fixes || fixes.length === 0 ? (
        <Typography color="text.secondary">No priority fixes — nothing flagged.</Typography>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {fixes.map((f, i) => (
            <Box key={i} sx={{ pl: 2, borderLeft: "4px solid", borderColor: `${sevColor(f.severity)}.main` }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                <Chip size="small" color={sevColor(f.severity)} variant="outlined" label={sevLabel(f.severity)} />
                <Typography component="span" sx={{ fontWeight: 700, color: "text.secondary" }}>
                  {f.step_id}
                </Typography>
                <Typography component="span" sx={{ fontWeight: 600 }}>
                  {f.text}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
                  {f.ease} effort
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {f.how_to}
              </Typography>
              {f.coverage_delta > 0 && (
                <Typography variant="caption" sx={{ color: "success.main" }}>
                  fixing this lifts coverage by {(f.coverage_delta * 100).toFixed(0)} pts
                </Typography>
              )}
            </Box>
          ))}
        </Box>
      )}
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
