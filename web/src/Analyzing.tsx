import CheckIcon from "@mui/icons-material/Check";
import { Box, CircularProgress, Typography, useMediaQuery, useTheme } from "@mui/material";
import { Fragment } from "react";
import { HeroShell } from "./HeroShell";

type StepState = "pending" | "running" | "done";
const CIRCLE = 52; // px — node diameter; connectors align to its centre (CIRCLE / 2)

// The immersive "Analyzing" page: same bold hero as the landing (no card), with a connected
// flow-chart stepper instead of loose dots. Each step is a circle — hollow when pending, a spinning
// ring while running, a filled checkmark once done — joined by connectors that fill in as the run
// advances. Horizontal on desktop, vertical on phones.
export function Analyzing({
  stageState,
  stages,
  source,
  mode,
}: {
  stageState: Record<string, "running" | "done">;
  stages: readonly string[];
  source?: string;
  mode: "full" | "local";
}) {
  return (
    <HeroShell mode={mode}>
      <Box sx={{ textAlign: "center", maxWidth: 760, mx: "auto" }}>
        <Typography variant="h3" sx={{ fontWeight: 700, letterSpacing: "-0.02em", fontSize: { xs: "1.75rem", md: "2.25rem" } }}>
          Analyzing
        </Typography>
        {source && (
          <Typography sx={{ mt: 1, color: "rgba(255,255,255,0.78)", wordBreak: "break-all" }}>
            {source}
          </Typography>
        )}
        <Box sx={{ mt: { xs: 5, md: 7 } }}>
          <StepFlow stages={stages} stageState={stageState} />
        </Box>
      </Box>
    </HeroShell>
  );
}

function StepFlow({
  stages,
  stageState,
}: {
  stages: readonly string[];
  stageState: Record<string, "running" | "done">;
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
  const color = filled ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.22)";
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
          color: state === "pending" ? "rgba(255,255,255,0.6)" : "common.white",
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
      <Box sx={{ ...base, bgcolor: "common.white", color: "primary.main" }}>
        <CheckIcon sx={{ fontSize: 28 }} />
      </Box>
    );
  }
  if (state === "running") {
    return (
      <Box sx={{ ...base }}>
        {/* faint full ring as a track, with the spinner on top */}
        <CircularProgress size={CIRCLE} thickness={3.5} sx={{ color: "rgba(255,255,255,0.25)", position: "absolute" }} variant="determinate" value={100} />
        <CircularProgress size={CIRCLE} thickness={3.5} sx={{ color: "common.white" }} />
      </Box>
    );
  }
  // pending: hollow outline
  return <Box sx={{ ...base, border: "3px solid rgba(255,255,255,0.3)" }} />;
}
