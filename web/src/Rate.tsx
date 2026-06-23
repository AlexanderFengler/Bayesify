import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import {
  Alert,
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
import { TopBar } from "./HeroShell";
import { STATUS_LABEL, STATUS_OPTIONS } from "./rubric";
import { StepCardShell } from "./StepCard";
import type { StepStatus } from "./types";

type Relevance = "" | "yes" | "partial" | "no";
type PaperClass = "" | "empirical" | "numerical_experiment" | "methodological";

interface StepDraft {
  status: "" | StepStatus;
  confidence: number;
  rationale: string;
  cited: number[]; // indices into ctx.evidence
  missingSubtag: "" | "not-done" | "not-reported-suspected";
}
const EMPTY: StepDraft = { status: "", confidence: 0.8, rationale: "", cited: [], missingSubtag: "" };

const INFERENCE = ["mcmc", "hmc_nuts", "variational", "exact_analytic", "unstated"];
const PRIORS = ["informative", "weakly_informative", "default", "none", "unstated"];
const CLASSES: { v: PaperClass; label: string }[] = [
  { v: "empirical", label: "empirical" },
  { v: "numerical_experiment", label: "numerical experiment" },
  { v: "methodological", label: "methodological" },
];

// The colour a status chip wears — mirrors the report's status palette so the two views read alike.
const CHIP_COLOR: Record<StepStatus, "success" | "warning" | "error" | "default"> = {
  done_well: "success",
  partial: "warning",
  missing: "error",
  not_applicable: "default",
};

// Full-bleed page shell shared by every state of the rating flow (loading / error / done / form), so
// the top bar and width stay constant. Mirrors Report/Inventory's `Box > TopBar > Container` chrome.
function RateShell({ mode, children }: { mode: "full" | "local"; children: React.ReactNode }) {
  return (
    <Box
      sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column", bgcolor: "background.default" }}
    >
      <TopBar mode={mode} />
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="md" sx={{ py: { xs: 3, md: 5 } }}>
          {children}
        </Container>
      </Box>
    </Box>
  );
}

// The blind rating form: a rater walks the same rubric the engine walks and authors a Rating,
// WITHOUT ever seeing the engine's verdict (the context endpoint serves no ScoredResult). Statuses
// start blank — nothing is pre-filled from the engine or the gate resolver, so the rater judges cold.
export function Rate({
  paperId,
  mode,
  onExit,
}: {
  paperId: string;
  mode: "full" | "local";
  onExit: () => void;
}) {
  const [ctx, setCtx] = useState<RateContext | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [profile, setProfile] = useState("synthesis"); // which rubric the rater rates against
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [raterId, setRaterId] = useState("rater-1");
  const [relationship, setRelationship] = useState("independent");
  const [relevance, setRelevance] = useState<Relevance>("");
  const [relevanceRationale, setRelevanceRationale] = useState("");
  const [paperClass, setPaperClass] = useState<PaperClass>("");
  const [classRationale, setClassRationale] = useState("");
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
    fetchRateContext(paperId, profile)
      .then(setCtx)
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));
  }, [paperId, profile]);

  const draft = (id: string) => perStep[id] ?? EMPTY;
  const setStep = (id: string, patch: Partial<StepDraft>) =>
    setPerStep((prev) => ({ ...prev, [id]: { ...(prev[id] ?? EMPTY), ...patch } }));
  const toggleCite = (id: string, i: number) => {
    const cur = draft(id).cited;
    setStep(id, { cited: cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i] });
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
        paper_class_label: null,
        paper_class_rationale: "",
        gate_facts: null,
        steps: [],
      };
    }
    if (!paperClass) return { error: "Choose a paper type." };
    const steps = [];
    for (const s of ctx!.rubric.steps) {
      const d = draft(s.id);
      if (!d.status) continue; // an unrated step is omitted (a partial pass is allowed)
      const applicable = d.status !== "not_applicable";
      if (applicable && !d.rationale.trim()) return { error: `${s.id}: add a rationale.` };
      if ((d.status === "done_well" || d.status === "partial") && d.cited.length === 0)
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
      paper_class_label: paperClass,
      paper_class_rationale: classRationale,
      gate_facts: gate,
      steps,
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
      await submitRating(paperId, r, profile);
      setDone(true);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loadErr) {
    return (
      <RateShell mode={mode}>
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
      <RateShell mode={mode}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 6 }}>
          <CircularProgress size={20} />
          <Typography>Loading the rating context…</Typography>
        </Box>
      </RateShell>
    );
  }

  if (done) {
    return (
      <RateShell mode={mode}>
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
    <RateShell mode={mode}>
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
          label="Relevance — is this a Bayesian-workflow paper?"
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
            <TextField
              select
              fullWidth
              size="small"
              label="Paper type"
              value={paperClass}
              onChange={(e) => setPaperClass(e.target.value as PaperClass)}
            >
              <MenuItem value="">— choose —</MenuItem>
              {CLASSES.map((c) => (
                <MenuItem key={c.v} value={c.v}>
                  {c.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              fullWidth
              multiline
              minRows={2}
              size="small"
              label="Paper type rationale (optional)"
              value={classRationale}
              onChange={(e) => setClassRationale(e.target.value)}
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
                {INFERENCE.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
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
                {PRIORS.map((v) => (
                  <MenuItem key={v} value={v}>
                    {v}
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
                  {s.done_well && (
                    <Typography variant="body2" color="text.secondary">
                      <strong>Done well:</strong> {s.done_well}
                    </Typography>
                  )}
                  {s.done_poorly && (
                    <Typography variant="body2" color="text.disabled">
                      <strong>Done poorly:</strong> {s.done_poorly}
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
                      {(d.status === "done_well" || d.status === "partial") && (
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
          bgcolor: "background.default",
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
