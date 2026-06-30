import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DescriptionIcon from "@mui/icons-material/Description";
import {
  Box,
  Button,
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
import { HeroShell } from "./HeroShell";

// The immersive landing page (first screen of the MUI migration). A bold accent hero band fills the
// viewport: brand + headline + blurb on the left, the upload panel on a light surface on the right.
// Collapses to a single stacked column on phones. This screen is fully MUI — it does NOT use the
// legacy .page/.container chrome; App renders it directly for the idle/landing state.
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
    <HeroShell maxWidth="xl">
      {/* two columns: pitch | upload panel */}
      <Box
        sx={{
          display: "flex",
          flexDirection: { xs: "column", md: "row" },
          gap: { xs: 4, md: 10 },
          alignItems: { xs: "stretch", md: "center" },
        }}
      >
        <Box sx={{ flex: "1 1 0", minWidth: 0 }}>
          {/* the title sets the column width; the subcaption (width:0; min-width:100%) fills that
              same width without widening it, so the two blocks share an exact right edge */}
          <Box sx={{ width: "fit-content", maxWidth: "100%" }}>
            <Typography
              variant="h2"
              sx={{
                fontWeight: 700,
                lineHeight: 1.1,
                letterSpacing: "-0.02em",
                fontSize: { xs: "2rem", sm: "2.75rem", md: "3.25rem" },
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
                color: "text.secondary",
                width: 0,
                minWidth: "100%",
              }}
            >
              Drop a PDF or paste an identifier. You will get a per-step report with a coverage and
              a quality score. Every finding is grounded in the paper and in the methodological
              literature.
            </Typography>
          </Box>
        </Box>

        <Box sx={{ flex: "1 1 0", minWidth: 0, width: "100%" }}>
          <UploadPanel {...p} canStart={canStart} rubricOptions={rubricOptions} />
        </Box>
      </Box>
    </HeroShell>
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
        to="/rubrics"
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
            AI
          </ToggleButton>
          <ToggleButton value="human" sx={{ px: 2 }}>
            Human
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
