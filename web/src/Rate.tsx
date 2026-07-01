import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControlLabel,
  MenuItem,
  Paper,
  Slider,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import {
  fetchRateContext,
  fetchRubrics,
  type RateContext,
  type RatingInput,
  type RubricSummary,
  submitRating,
} from "./api";
import { STATUS_LABEL, STATUS_OPTIONS } from "./rubric";
import { StepCardShell } from "./StepCard";
import type { StepStatus } from "./types";

type Relevance = "" | "yes" | "partial" | "no";
type PaperClass =
  | "model_development"
  | "method_development"
  | "software_development"
  | "data_analysis"
  | "numerical_analysis"
  | "theoretical_analysis"
  | "review";

interface StepDraft {
  status: "" | StepStatus;
  confidence: number;
  rationale: string;
  cited: number[]; // indices into ctx.evidence
  missingSubtag: "" | "not-done" | "not-reported-suspected";
}
const EMPTY: StepDraft = { status: "", confidence: 0.8, rationale: "", cited: [], missingSubtag: "" };

const INFERENCE = [
  { value: "mcmc", label: "MCMC" },
  { value: "hmc_nuts", label: "HMC / NUTS" },
  { value: "variational", label: "Variational" },
  { value: "sbi", label: "SBI" },
  { value: "exact_analytic", label: "Exact / analytic" },
  { value: "unstated", label: "Unstated" },
];
const PRIORS = [
  { value: "informative", label: "Informative" },
  { value: "weakly_informative", label: "Weakly informative" },
  { value: "default", label: "Default" },
  { value: "none", label: "None" },
  { value: "unstated", label: "Unstated" },
];
const CLASSES: { value: PaperClass; label: string }[] = [
  { value: "model_development", label: "Model development" },
  { value: "method_development", label: "Method development" },
  { value: "software_development", label: "Software development" },
  { value: "data_analysis", label: "Data analysis" },
  { value: "numerical_analysis", label: "Numerical analysis" },
  { value: "theoretical_analysis", label: "Theoretical analysis" },
  { value: "review", label: "Review" },
];

// The colour a status chip wears — mirrors the report's status palette so the two views read alike.
const CHIP_COLOR: Record<StepStatus, "success" | "warning" | "error" | "default"> = {
  adequate: "success",
  partial: "warning",
  missing: "error",
  not_applicable: "default",
};

// Width-constrained shell shared by every state of the rating flow (loading / error / done / form),
// so the column width stays constant. The header is permanent (Layout) and lives above this.
function RateShell({ children }: { children: React.ReactNode }) {
  return (
    <Container maxWidth="md" sx={{ py: { xs: 3, md: 5 } }}>
      {children}
    </Container>
  );
}

// The blind rating form: a rater walks the same rubric the engine walks and authors a Rating,
// WITHOUT ever seeing the engine's verdict (the context endpoint serves no ScoredResult). Statuses
// start blank — nothing is pre-filled from the engine or the gate resolver, so the rater judges cold.
export function Rate({
  paperId,
  onExit,
  pending = false,
}: {
  paperId: string;
  onExit: () => void;
  pending?: boolean; // a background run is still producing the rating context — show loading, don't fetch yet
}) {
  const [ctx, setCtx] = useState<RateContext | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [profile, setProfile] = useState("synthesis"); // which rubric the rater rates against
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [raterId, setRaterId] = useState("rater-1");
  const [relationship, setRelationship] = useState("independent");
  const [relevance, setRelevance] = useState<Relevance>("");
  const [relevanceRationale, setRelevanceRationale] = useState("");
  const [paperClasses, setPaperClasses] = useState<PaperClass[]>([]);
  const [classRationale, setClassRationale] = useState("");
  const [tags, setTags] = useState<string[]>([]); // freeform tags → the paper's Archive entry
  const [gate, setGate] = useState({
    inference_method: "mcmc",
    n_models: 1,
    bf_claimed: false,
    prior_informativeness: "weakly_informative",
  });
  const [perStep, setPerStep] = useState<Record<string, StepDraft>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    fetchRubrics()
      .then(setRubrics)
      .catch(() => {});
  }, []);

  useEffect(() => {
    setCtx(null);
    setPerStep({}); // a different rubric has different steps — clear stale per-step drafts
    if (pending) return; // wait for the background run to finish; ctx stays null → loading state
    fetchRateContext(paperId, profile)
      .then(setCtx)
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));
  }, [paperId, profile, pending]);

  const draft = (id: string) => perStep[id] ?? EMPTY;
  const setStep = (id: string, patch: Partial<StepDraft>) =>
    setPerStep((prev) => ({ ...prev, [id]: { ...(prev[id] ?? EMPTY), ...patch } }));
  const toggleCite = (id: string, i: number) => {
    const cur = draft(id).cited;
    setStep(id, { cited: cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i] });
  };
  const togglePaperClass = (value: PaperClass) => {
    setPaperClasses((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
  };

  function build(): RatingInput | { error: string } {
    if (!relevance) return { error: "Choose a relevance verdict." };
    if (!relevanceRationale.trim()) return { error: "Add a relevance rationale." };
    const base = { rater_id: raterId.trim() || "rater-1", relationship };
    if (relevance === "no") {
      return {
        ...base,
        relevance_label: "no",
        relevance_rationale: relevanceRationale,
        paper_class_labels: [],
        paper_class_rationale: "",
        gate_facts: null,
        steps: [],
        tags,
      };
    }
    if (paperClasses.length === 0) return { error: "Choose at least one paper type." };
    const steps = [];
    for (const s of ctx!.rubric.steps) {
      const d = draft(s.id);
      if (!d.status) continue; // an unrated step is omitted (a partial pass is allowed)
      const applicable = d.status !== "not_applicable";
      if (applicable && !d.rationale.trim()) return { error: `${s.id}: add a rationale.` };
      if ((d.status === "adequate" || d.status === "partial") && d.cited.length === 0)
        return { error: `${s.id}: cite ≥1 evidence span for a "${STATUS_LABEL[d.status]}" rating.` };
      steps.push({
        step_id: s.id,
        applicable,
        status: d.status,
        confidence: d.confidence,
        rationale: applicable ? d.rationale : "",
        evidence: d.cited.map((i) => ({
          section_id: ctx!.evidence[i].section_id,
          page: ctx!.evidence[i].page,
          quote: ctx!.evidence[i].quote,
        })),
        missing_subtag: d.status === "missing" && d.missingSubtag ? d.missingSubtag : null,
      });
    }
    if (steps.length === 0) return { error: "Rate at least one step." };
    return {
      ...base,
      relevance_label: relevance,
      relevance_rationale: relevanceRationale,
      paper_class_labels: paperClasses,
      paper_class_rationale: classRationale,
      gate_facts: gate,
      steps,
      tags,
    };
  }

  async function onSubmit() {
    const r = build();
    if ("error" in r) {
      setFormError(r.error);
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      await submitRating(paperId, r, profile, {
        source_sha256: ctx?.source_sha256,
        version_label: ctx?.version_label,
      });
      setDone(true);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loadErr) {
    return (
      <RateShell>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={onExit}>
              Back
            </Button>
          }
        >
          <Typography sx={{ fontWeight: 600 }}>Couldn&rsquo;t load the rating context</Typography>
          {loadErr}
        </Alert>
      </RateShell>
    );
  }
  if (!ctx) {
    return (
      <RateShell>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 6 }}>
          <CircularProgress size={20} />
          <Typography>Loading the rating context…</Typography>
        </Box>
      </RateShell>
    );
  }

  if (done) {
    return (
      <RateShell>
        <Paper variant="outlined" sx={{ p: { xs: 3, md: 4 }, borderRadius: 3, textAlign: "center" }}>
          <Chip color="success" label="Rating recorded" sx={{ mb: 2, fontWeight: 600 }} />
          <Typography sx={{ maxWidth: 520, mx: "auto", color: "text.secondary" }}>
            Your blind rating of <strong>{ctx.source_label}</strong> was saved. Two-to-three blind
            ratings plus an adjudicated consensus assemble into the gold record (at adjudication).
          </Typography>
          <Button variant="contained" disableElevation onClick={onExit} sx={{ mt: 3 }}>
            Done
          </Button>
        </Paper>
      </RateShell>
    );
  }

  const relevant = relevance !== "" && relevance !== "no";
  const rubricOptions = rubrics.length ? rubrics : [{ id: profile, label: profile }];
  const ratedCount = ctx.rubric.steps.filter((s) => draft(s.id).status).length;

  return (
    <RateShell>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.08em" }}>
            Blind rating
          </Typography>
          <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
            {ctx.source_label}
          </Typography>
        </Box>
        <Button variant="outlined" onClick={onExit} sx={{ flexShrink: 0 }}>
          Cancel
        </Button>
      </Box>

      <Alert severity="info" icon={<VisibilityOffIcon />} sx={{ mt: 2.5 }}>
        You are rating <strong>blind</strong> — the engine&rsquo;s verdict is hidden. Judge each step
        from the paper and the detected evidence only; nothing here is pre-filled.
      </Alert>

      <Paper
        variant="outlined"
        sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3, mt: 2.5, display: "flex", flexDirection: "column", gap: 2.5 }}
      >
        <TextField
          select
          fullWidth
          size="small"
          label="Rubric"
          value={profile}
          onChange={(e) => setProfile(e.target.value)}
        >
          {rubricOptions.map((r) => (
            <MenuItem key={r.id} value={r.id}>
              {r.label}
            </MenuItem>
          ))}
        </TextField>
        {ctx.rubric.summary && (
          <Typography variant="body2" color="text.secondary">
            {ctx.rubric.summary}
          </Typography>
        )}

        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          <TextField
            size="small"
            label="Rater id"
            value={raterId}
            onChange={(e) => setRaterId(e.target.value)}
            sx={{ flex: "1 1 180px" }}
          />
          <TextField
            select
            size="small"
            label="Relationship"
            value={relationship}
            onChange={(e) => setRelationship(e.target.value)}
            sx={{ flex: "1 1 180px" }}
          >
            <MenuItem value="independent">independent</MenuItem>
            <MenuItem value="engine_dev">engine developer</MenuItem>
            <MenuItem value="prompt_author">prompt author</MenuItem>
          </TextField>
        </Box>

        <Divider />

        <TextField
          select
          fullWidth
          size="small"
          label="Relevance - is a Bayesian workflow applicable?"
          value={relevance}
          onChange={(e) => setRelevance(e.target.value as Relevance)}
        >
          <MenuItem value="">— choose —</MenuItem>
          <MenuItem value="yes">yes</MenuItem>
          <MenuItem value="partial">partial</MenuItem>
          <MenuItem value="no">no</MenuItem>
        </TextField>
        <TextField
          fullWidth
          multiline
          minRows={2}
          size="small"
          label="Relevance rationale"
          required
          placeholder="Why?"
          value={relevanceRationale}
          onChange={(e) => setRelevanceRationale(e.target.value)}
        />

        {relevant && (
          <>
            <Divider />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                Paper type
              </Typography>
              <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", mt: 0.75 }}>
                {CLASSES.map((c) => (
                  <FormControlLabel
                    key={c.value}
                    sx={{
                      m: 0,
                      pr: 1.25,
                      border: 1,
                      borderColor: paperClasses.includes(c.value) ? "primary.main" : "divider",
                      borderRadius: 1,
                      bgcolor: paperClasses.includes(c.value) ? "action.selected" : "transparent",
                    }}
                    control={
                      <Checkbox
                        size="small"
                        checked={paperClasses.includes(c.value)}
                        onChange={() => togglePaperClass(c.value)}
                      />
                    }
                    label={c.label}
                  />
                ))}
              </Box>
            </Box>
            <TextField
              fullWidth
              multiline
              minRows={2}
              size="small"
              label="Paper type rationale (optional)"
              value={classRationale}
              onChange={(e) => setClassRationale(e.target.value)}
            />
            {/* Freeform tags for your Archive — independent of the blind judgment (curation only). */}
            <Autocomplete
              multiple
              freeSolo
              size="small"
              options={[]}
              value={tags}
              onChange={(_, v) => setTags(v as string[])}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Tags (optional)"
                  placeholder={tags.length ? "" : "Add tags — press Enter"}
                  helperText="Freeform labels to find this paper later in the Archive"
                />
              )}
            />
            <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
              <TextField
                select
                size="small"
                label="Inference"
                value={gate.inference_method}
                onChange={(e) => setGate({ ...gate, inference_method: e.target.value })}
                sx={{ flex: "1 1 160px" }}
              >
                {INFERENCE.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                type="number"
                size="small"
                label="# models"
                value={gate.n_models}
                onChange={(e) => setGate({ ...gate, n_models: Math.max(1, +e.target.value) })}
                slotProps={{ htmlInput: { min: 1 } }}
                sx={{ flex: "0 1 110px" }}
              />
              <TextField
                select
                size="small"
                label="Priors"
                value={gate.prior_informativeness}
                onChange={(e) => setGate({ ...gate, prior_informativeness: e.target.value })}
                sx={{ flex: "1 1 160px" }}
              >
                {PRIORS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={gate.bf_claimed}
                    onChange={(e) => setGate({ ...gate, bf_claimed: e.target.checked })}
                  />
                }
                label="Bayes factor claimed"
              />
            </Box>
          </>
        )}
      </Paper>

      {relevance === "no" && (
        <Alert severity="info" sx={{ mt: 2.5 }}>
          Marked not a Bayesian-workflow paper — there are no steps to rate. Submit to record it.
        </Alert>
      )}

      {relevant && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 2.5 }}>
          {ctx.rubric.steps.map((s) => {
            const d = draft(s.id);
            const na = d.status === "not_applicable";
            return (
              <StepCardShell
                key={s.id}
                stepId={s.id}
                stepName={s.name}
                status={d.status}
                pill={
                  <Chip
                    size="small"
                    label={d.status ? STATUS_LABEL[d.status] : "rate"}
                    color={d.status ? CHIP_COLOR[d.status] : "default"}
                    variant={d.status ? "filled" : "outlined"}
                  />
                }
              >
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: 0.5 }}>
                  {s.adequate && (
                    <Typography variant="body2" color="text.secondary">
                      <strong>Adequate:</strong> {s.adequate}
                    </Typography>
                  )}
                  {s.missing && (
                    <Typography variant="body2" color="text.disabled">
                      <strong>Missing:</strong> {s.missing}
                    </Typography>
                  )}

                  <TextField
                    select
                    size="small"
                    label="Rating"
                    value={d.status}
                    onChange={(e) => setStep(s.id, { status: e.target.value as StepStatus | "" })}
                    sx={{ alignSelf: "flex-start", minWidth: 200 }}
                  >
                    <MenuItem value="">— rate this step —</MenuItem>
                    {STATUS_OPTIONS.map((st) => (
                      <MenuItem key={st} value={st}>
                        {STATUS_LABEL[st]}
                      </MenuItem>
                    ))}
                  </TextField>

                  {d.status && !na && (
                    <>
                      <Box sx={{ maxWidth: 280 }}>
                        <Typography variant="caption" color="text.secondary">
                          Confidence: {Math.round(d.confidence * 100)}%
                        </Typography>
                        <Slider
                          size="small"
                          min={0}
                          max={1}
                          step={0.05}
                          value={d.confidence}
                          onChange={(_, v) => setStep(s.id, { confidence: v as number })}
                          valueLabelDisplay="auto"
                          valueLabelFormat={(v) => `${Math.round(v * 100)}%`}
                        />
                      </Box>
                      <TextField
                        fullWidth
                        multiline
                        minRows={2}
                        size="small"
                        label="Rationale"
                        required
                        value={d.rationale}
                        onChange={(e) => setStep(s.id, { rationale: e.target.value })}
                      />
                      {(d.status === "adequate" || d.status === "partial") && (
                        <EvidenceCite
                          spans={ctx.evidence}
                          cited={d.cited}
                          onToggle={(i) => toggleCite(s.id, i)}
                        />
                      )}
                      {d.status === "missing" && (
                        <TextField
                          select
                          size="small"
                          label="Missing because (optional)"
                          value={d.missingSubtag}
                          onChange={(e) =>
                            setStep(s.id, { missingSubtag: e.target.value as StepDraft["missingSubtag"] })
                          }
                          sx={{ alignSelf: "flex-start", minWidth: 220 }}
                        >
                          <MenuItem value="">— optional —</MenuItem>
                          <MenuItem value="not-done">not done</MenuItem>
                          <MenuItem value="not-reported-suspected">done but not reported</MenuItem>
                        </TextField>
                      )}
                    </>
                  )}
                </Box>
              </StepCardShell>
            );
          })}
        </Box>
      )}

      {formError && (
        <Alert severity="error" sx={{ mt: 2.5 }}>
          {formError}
        </Alert>
      )}

      <Box
        sx={{
          position: "sticky",
          bottom: 0,
          mt: 2.5,
          py: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          bgcolor: (t) => t.tokens.glass,
          backdropFilter: "blur(14px)",
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <Typography variant="body2" color="text.secondary">
          {relevant ? `${ratedCount} of ${ctx.rubric.steps.length} steps rated` : " "}
        </Typography>
        <Button variant="contained" disableElevation disabled={submitting} onClick={onSubmit}>
          {submitting ? "Saving…" : "Submit blind rating"}
        </Button>
      </Box>
    </RateShell>
  );
}

function EvidenceCite({
  spans,
  cited,
  onToggle,
}: {
  spans: RateContext["evidence"];
  cited: number[];
  onToggle: (i: number) => void;
}) {
  if (spans.length === 0) {
    return (
      <Typography variant="caption" color="text.disabled">
        No detector spans to cite for this paper. (Free-quote citation is a later enhancement.)
      </Typography>
    );
  }
  return (
    <Box sx={{ borderLeft: 2, borderColor: "divider", pl: 1.5, py: 0.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        Cite the evidence you saw (≥1 for present)
      </Typography>
      {spans.map((e, i) => (
        <FormControlLabel
          key={i}
          sx={{ display: "flex", alignItems: "flex-start", m: 0, mt: 0.5 }}
          control={
            <Checkbox
              size="small"
              checked={cited.includes(i)}
              onChange={() => onToggle(i)}
              sx={{ py: 0, mr: 0.5 }}
            />
          }
          label={
            <Typography variant="body2">
              &ldquo;{e.quote}&rdquo;{" "}
              <Box component="cite" sx={{ color: "text.disabled", fontStyle: "normal" }}>
                §{e.section_id}
              </Box>
            </Typography>
          }
        />
      ))}
    </Box>
  );
}
