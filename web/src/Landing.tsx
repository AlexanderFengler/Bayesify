import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DescriptionIcon from "@mui/icons-material/Description";
import {
  Box,
  Button,
  Container,
  Divider,
  Link,
  MenuItem,
  Paper,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import type { RubricSummary } from "./api";
import { GoldText } from "./GoldText";
import { Guide, ReviewerTokenField } from "./Guide";
import { Rubrics } from "./Rubrics";

// The main page — the first (and only) landing screen. A bold hero band fills the initial viewport:
// headline + blurb on the left, the upload panel on the right; scrolling continues into the
// "How it works" and "Rubrics" sections (anchored #how-it-works / #rubrics for the footer nav), so
// the whole pitch reads as one page. Collapses to a single stacked column on phones.
//
// Layout uses Box + sx flex rather than MUI <Stack> (Stack's overloaded typing is broken under
// @mui/material v9 + @types/react 18); flex `gap` uses the same theme spacing units Stack would.
export interface LandingProps {
  mode: "full" | "local";
  setMode: (m: "full" | "local") => void;
  profile: string;
  setProfile: (p: string) => void;
  rubrics: RubricSummary[];
  identifier: string;
  setIdentifier: (s: string) => void;
  file: File | null;
  setFile: (f: File | null) => void;
  dragging: boolean;
  setDragging: (b: boolean) => void;
  fileInput: React.RefObject<HTMLInputElement>;
  onStart: (intent?: "analyze" | "rate") => void;
}

export function Landing(p: LandingProps) {
  const canStart = !!p.file || p.identifier.trim().length > 0;
  const rubricOptions = p.rubrics.length ? p.rubrics : [{ id: p.profile, label: p.profile }];

  return (
    <Box>
      {/* hero — fills the full height between the pinned header and footer (100cqh: the scroll area
          in Layout is a size query container), so the how-it-works and rubrics sections wait exactly
          below the fold. The dvh calc is a fallback for browsers without container-query units. */}
      <Box
        sx={{
          minHeight: "calc(100dvh - 220px)",
          "@supports (min-height: 100cqh)": { minHeight: "100cqh" },
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        <Container maxWidth="xl" sx={{ py: { xs: 4, md: 6 } }}>
          {/* two columns: pitch | upload panel */}
          <Box
            sx={{
              display: "flex",
              flexDirection: { xs: "column", md: "row" },
              gap: { xs: 4, md: 10 },
              alignItems: { xs: "stretch", md: "center" },
            }}
          >
            {/* pitch column — title and caption span the whole column, so both share the exact
                width of the upload panel across the gap */}
            <Box sx={{ flex: "1 1 0", minWidth: 0 }}>
              <Typography
                variant="h2"
                sx={{
                  fontWeight: 700,
                  lineHeight: 1.08,
                  letterSpacing: "-0.02em",
                  fontSize: { xs: "2rem", sm: "2.75rem", md: "3.5rem" },
                }}
              >
                {/* always three lines */}
                Put your
                <br />
                Bayesian workflow
                <br />
                to the test.
              </Typography>
              <Typography
                sx={{
                  mt: 3,
                  fontSize: { xs: "1rem", md: "1.2rem" },
                  lineHeight: 1.6,
                  color: "text.secondary",
                }}
              >
                Bayesify is a multi-stage agentic framework for evaluating the integrity of
                Bayesian workflows. Backed by curated rubrics from the methodological
                literature, it grades your paper step by step and helps you bring your workflow
                to the{" "}
                <GoldText>
                  <strong>gold standard</strong>
                </GoldText>
                .
              </Typography>
            </Box>

            <Box sx={{ flex: "1 1 0", minWidth: 0, width: "100%" }}>
              <UploadPanel {...p} canStart={canStart} rubricOptions={rubricOptions} />
            </Box>
          </Box>
        </Container>
      </Box>

      {/* the former standalone pages, folded in as scrollable sections of the main page */}
      <Divider />
      <Guide id="how-it-works" />
      <Divider />
      <Rubrics id="rubrics" />

      {/* reviewer plumbing lives at the very bottom of the page, out of the pitch's way */}
      <Divider />
      <Container maxWidth="xl" sx={{ py: { xs: 4, md: 6 } }}>
        <ReviewerTokenField />
      </Container>
    </Box>
  );
}

// The upload surface: the dropzone, the identifier fallback, the rubric picker, the mode toggle, and
// the two actions.
function UploadPanel(
  p: LandingProps & {
    canStart: boolean;
    rubricOptions: { id: string; label: string }[];
  },
) {
  // AI (engine analysis) vs Human (blind self-rating); AI is the default.
  const [intent, setIntent] = useState<"ai" | "human">("ai");
  return (
    <Paper
      elevation={0}
      // Highlighted like the rubric cards on hover: a primary-tinted border and glow, so the panel
      // stands out from the aurora in dark mode (the old flat dark drop-shadow vanished against it).
      sx={{
        p: { xs: 2.5, md: 3 },
        borderRadius: 3,
        border: "1px solid",
        borderColor: "primary.main",
        boxShadow: (t) => `0 14px 36px ${alpha(t.palette.primary.main, 0.22)}`,
      }}
    >
      {/* dropzone */}
      <Box
        onClick={() => p.fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          p.setDragging(true);
        }}
        onDragLeave={() => p.setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          p.setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) p.setFile(f);
        }}
        sx={{
          cursor: "pointer",
          textAlign: "center",
          px: 2,
          py: { xs: 3, md: 4 },
          borderRadius: 2,
          border: "2px dashed",
          borderColor: p.dragging ? "primary.main" : "divider",
          bgcolor: p.dragging ? "primary.light" : "transparent",
          transition: "border-color 120ms, background-color 120ms",
          "&:hover": { borderColor: "primary.main", bgcolor: "primary.light" },
        }}
      >
        <input
          ref={p.fileInput}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => p.setFile(e.target.files?.[0] ?? null)}
        />
        {p.file ? (
          <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", justifyContent: "center" }}>
            <DescriptionIcon color="primary" />
            <Typography sx={{ fontWeight: 600, wordBreak: "break-all" }}>{p.file.name}</Typography>
            <Link
              component="button"
              type="button"
              underline="hover"
              onClick={(e) => {
                e.stopPropagation();
                p.setFile(null);
              }}
            >
              remove
            </Link>
          </Box>
        ) : (
          <>
            <CloudUploadIcon sx={{ fontSize: 36, color: "text.secondary", mb: 1 }} />
            <Typography sx={{ fontWeight: 600 }}>Drop a PDF here</Typography>
            <Typography variant="body2" color="text.secondary">
              or click to choose a file
            </Typography>
          </>
        )}
      </Box>

      <Divider sx={{ my: 2.5 }}>
        <Typography variant="caption" color="text.secondary">
          or paste an identifier
        </Typography>
      </Divider>

      <TextField
        fullWidth
        size="small"
        placeholder="arXiv ID, DOI, OpenAlex ID, or URL"
        value={p.identifier}
        onChange={(e) => p.setIdentifier(e.target.value)}
        disabled={!!p.file}
      />

      <TextField
        select
        fullWidth
        size="small"
        label="Rubric"
        value={p.profile}
        onChange={(e) => p.setProfile(e.target.value)}
        sx={{ mt: 2 }}
      >
        {p.rubricOptions.map((r) => (
          <MenuItem key={r.id} value={r.id}>
            {r.label}
          </MenuItem>
        ))}
      </TextField>
      <Link
        component={RouterLink}
        to="/#rubrics"
        variant="body2"
        underline="hover"
        sx={{ display: "inline-block", mt: 1, fontWeight: 600 }}
      >
        See how our rubrics compare →
      </Link>

      <Box
        sx={{
          display: "flex",
          flexDirection: { xs: "column", sm: "row" },
          gap: 2,
          alignItems: { xs: "stretch", sm: "center" },
          justifyContent: "space-between",
          mt: 2.5,
        }}
      >
        {/* Who assesses the paper: "AI" runs the engine (the connected analysis); "Human" opens the
            blind self-rating form. AI is the default. The privacy mode stays "full" — Local is hidden. */}
        <ToggleButtonGroup
          exclusive
          size="small"
          value={intent}
          onChange={(_, v) => v && setIntent(v)}
          aria-label="who assesses the paper"
        >
          <ToggleButton value="ai" sx={{ px: 2 }}>
            AI Agent
          </ToggleButton>
          <ToggleButton value="human" sx={{ px: 2 }}>
            Human Expert
          </ToggleButton>
        </ToggleButtonGroup>

        <Box sx={{ display: "flex", gap: 1, alignItems: "center", justifyContent: "flex-end" }}>
          <Button
            variant="contained"
            disableElevation
            disabled={!p.canStart}
            onClick={() => p.onStart(intent === "human" ? "rate" : "analyze")}
            title={
              intent === "human"
                ? "Rate this paper yourself against the rubric, blind to the engine's verdict"
                : undefined
            }
          >
            {intent === "human" ? "Rate it yourself" : "Analyze"}
          </Button>
        </Box>
      </Box>
    </Paper>
  );
}
