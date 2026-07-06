import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import { Box, Button, CircularProgress, Typography, useMediaQuery, useTheme } from "@mui/material";
import { Fragment, useEffect, useState } from "react";
import { HeroShell } from "./HeroShell";
import { MathText } from "./MathText";

type StepState = "pending" | "running" | "done" | "failed";
const CIRCLE = 52; // px — node diameter; connectors align to its centre (CIRCLE / 2)

// The gate stop, rendered on this page when the engine decides the paper is out of scope: which
// verdict it was (relevance gate vs paper-type), the engine's reasons, and the two ways out.
export interface GateFailure {
  isReview: boolean; // true → the paper-type gate (a review/opinion piece); false → the relevance gate
  rationale: string;
  confidence: number;
  onRerun: () => void; // the escape hatch: override the gate and grade anyway
  onReset: () => void; // start over with another paper
}

// The rotating "working…" words for the title, typed out one at a time (à la a CLI status line).
const WORKING_WORDS = [
  "Bayesifying",
  "Distilling",
  "Perusing",
  "Contemplating",
  "Meditating",
  "Reasoning",
  "Triple-checking",
  "Recognizing",
  "Evaluating",
  "Rubricking"
];

// A typewriter that types a word, holds, deletes, then moves to the next — looping forever.
function useTypewriter(words: string[], { typeMs = 85, deleteMs = 40, holdMs = 1200 } = {}) {
  const [text, setText] = useState("");
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<"typing" | "holding" | "deleting">("typing");

  useEffect(() => {
    const word = words[idx % words.length];
    if (phase === "typing") {
      if (text.length < word.length) {
        const t = setTimeout(() => setText(word.slice(0, text.length + 1)), typeMs);
        return () => clearTimeout(t);
      }
      const t = setTimeout(() => setPhase("holding"), holdMs);
      return () => clearTimeout(t);
    }
    if (phase === "holding") {
      const t = setTimeout(() => setPhase("deleting"), holdMs);
      return () => clearTimeout(t);
    }
    // deleting
    if (text.length > 0) {
      const t = setTimeout(() => setText(word.slice(0, text.length - 1)), deleteMs);
      return () => clearTimeout(t);
    }
    setIdx((i) => (i + 1) % words.length);
    setPhase("typing");
  }, [text, phase, idx, words, typeMs, deleteMs, holdMs]);

  return text;
}

// The immersive "Analyzing" page: same bold hero as the landing (no card), with a connected
// flow-chart stepper instead of loose dots. Each step is a circle — hollow when pending, a spinning
// ring while running, a filled checkmark once done, a red cross when the run stopped there — joined
// by connectors that fill in as the run advances. Horizontal on desktop, vertical on phones.
// When `gate` is set the run ended at a gate: the typewriter gives way to a static verdict and the
// engine's reasons (plus the override / start-over actions) render beneath the flow.
export function Analyzing({
  stageState,
  stages,
  source,
  byline,
  gate,
}: {
  stageState: Record<string, "running" | "done" | "failed">;
  stages: readonly string[];
  source?: string;
  byline?: string | null;
  gate?: GateFailure | null;
}) {
  const typed = useTypewriter(WORKING_WORDS);
  return (
    <HeroShell>
      {/* left-aligned, sharing the flow diagram's left edge below */}
      <Box sx={{ maxWidth: 760, mx: "auto", textAlign: "left" }}>
        <Typography
          variant="h3"
          sx={{ fontWeight: 700, letterSpacing: "-0.02em", fontSize: { xs: "1.75rem", md: "2.25rem" }, minHeight: "1.3em" }}
        >
          {gate ? (
            "Out of scope."
          ) : (
            <>
              {typed}
              <Box
                component="span"
                aria-hidden
                sx={{
                  display: "inline-block",
                  ml: "2px",
                  fontWeight: 400,
                  animation: "caretBlink 1s steps(1) infinite",
                  "@keyframes caretBlink": { "0%,50%": { opacity: 1 }, "50.01%,100%": { opacity: 0 } },
                }}
              >
                ▌
              </Box>
            </>
          )}
        </Typography>
        {source && (
          <Typography sx={{ mt: 1, color: "text.secondary", wordBreak: "break-word" }}>
            {source}
          </Typography>
        )}
        {byline && (
          <Typography variant="body2" sx={{ mt: 0.5, color: "text.secondary" }}>
            {byline}
          </Typography>
        )}
        <Box sx={{ mt: { xs: 5, md: 7 } }}>
          <StepFlow stages={stages} stageState={stageState} />
        </Box>
        {gate && <GatePanel gate={gate} />}
      </Box>
    </HeroShell>
  );
}

// Why the run stopped: the gate's verdict and rationale, plus the two ways out — override the gate
// and grade anyway, or start over with another paper.
function GatePanel({ gate }: { gate: GateFailure }) {
  const [busy, setBusy] = useState(false);
  return (
    <Box sx={{ mt: { xs: 5, md: 6 }, pl: 2.5, borderLeft: "4px solid", borderColor: "error.main" }}>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        {gate.isReview ? "The per-step rubric doesn’t apply here" : "This doesn’t appear to be a Bayesian application"}
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.75, color: "text.secondary" }}>
        {gate.isReview
          ? "This reads as a review / opinion / perspective piece about the Bayesian workflow rather than one applying it to data, so nothing was graded."
          : "The relevance gate found no Bayesian statistical methodology to assess, so nothing was graded."}
      </Typography>
      <Box sx={{ mt: 2 }}>
        <Typography variant="overline" color="text.secondary">
          Why · {Math.round(gate.confidence * 100)}% confidence
        </Typography>
        <Typography variant="body2">
          <MathText>{gate.rationale}</MathText>
        </Typography>
      </Box>
      <Box sx={{ mt: 2.5, display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        <Button
          variant="contained"
          disableElevation
          disabled={busy}
          onClick={() => {
            setBusy(true);
            gate.onRerun();
          }}
        >
          {busy ? "Re-running…" : "Run full assessment anyway"}
        </Button>
        <Button variant="outlined" onClick={gate.onReset}>
          Analyze another
        </Button>
      </Box>
    </Box>
  );
}

function StepFlow({
  stages,
  stageState,
}: {
  stages: readonly string[];
  stageState: Record<string, "running" | "done" | "failed">;
}) {
  const theme = useTheme();
  const horizontal = useMediaQuery(theme.breakpoints.up("sm"));
  const stateOf = (stage: string): StepState => stageState[stage] ?? "pending";

  // Nodes and connectors are siblings of the same flex line so every circle shares one baseline; the
  // connector sits at the circle's centre via its margin (NOT nested inside a node, which would push
  // that node's circle down and leave the first — connector-less — node sitting higher).
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: horizontal ? "row" : "column",
        alignItems: horizontal ? "flex-start" : "stretch",
        justifyContent: "center",
      }}
    >
      {stages.map((stage, i) => {
        const state = stateOf(stage);
        // a connector is "filled" once the node before it is done (progress has flowed past it)
        const prevDone = i > 0 && stateOf(stages[i - 1]) === "done";
        return (
          <Fragment key={stage}>
            {i > 0 && <Connector horizontal={horizontal} filled={prevDone} />}
            <StepNode state={state} label={stage} horizontal={horizontal} />
          </Fragment>
        );
      })}
    </Box>
  );
}

// The line joining two nodes — a sibling of the nodes, offset to line up with the circle's centre
// ((CIRCLE - thickness) / 2). Horizontal between columns, vertical down the gutter on phones.
function Connector({ horizontal, filled }: { horizontal: boolean; filled: boolean }) {
  const color = filled ? "primary.main" : "divider";
  const offset = `${(CIRCLE - 3) / 2}px`;
  return horizontal ? (
    <Box sx={{ flex: 1, height: 3, mt: offset, mx: 0.5, bgcolor: color, borderRadius: 2, transition: "background-color 200ms" }} />
  ) : (
    <Box sx={{ width: 3, height: 28, ml: offset, my: 0.5, bgcolor: color, borderRadius: 2, transition: "background-color 200ms" }} />
  );
}

function StepNode({ state, label, horizontal }: { state: StepState; label: string; horizontal: boolean }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: horizontal ? "column" : "row",
        alignItems: "center",
        gap: horizontal ? 1.25 : 2,
        // horizontal nodes share the row width evenly; vertical nodes hug the left gutter
        flex: horizontal ? "1 1 0" : "0 0 auto",
        minWidth: 0,
      }}
    >
      <NodeCircle state={state} />
      <Typography
        sx={{
          fontSize: "0.875rem",
          fontWeight: state === "pending" ? 400 : 600,
          textTransform: "capitalize",
          color: state === "pending" ? "text.disabled" : state === "failed" ? "error.main" : "text.primary",
          textAlign: "center",
        }}
      >
        {label}
      </Typography>
    </Box>
  );
}

function NodeCircle({ state }: { state: StepState }) {
  // common centred box at the fixed circle size
  const base = {
    position: "relative" as const,
    width: CIRCLE,
    height: CIRCLE,
    flex: "0 0 auto",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "50%",
  };

  if (state === "done") {
    return (
      <Box sx={{ ...base, bgcolor: "primary.main", color: "primary.contrastText" }}>
        <CheckIcon sx={{ fontSize: 28 }} />
      </Box>
    );
  }
  // the run stopped at this step (a gate said no) — a filled red circle with a cross
  if (state === "failed") {
    return (
      <Box sx={{ ...base, bgcolor: "error.main", color: "error.contrastText" }}>
        <CloseIcon sx={{ fontSize: 28 }} />
      </Box>
    );
  }
  if (state === "running") {
    return (
      <Box sx={{ ...base }}>
        {/* faint full ring as a track, with the spinner on top */}
        <CircularProgress size={CIRCLE} thickness={3.5} sx={{ color: "divider", position: "absolute" }} variant="determinate" value={100} />
        <CircularProgress size={CIRCLE} thickness={3.5} sx={{ color: "primary.main" }} />
      </Box>
    );
  }
  // pending: hollow outline
  return <Box sx={{ ...base, border: "3px solid", borderColor: "divider" }} />;
}
