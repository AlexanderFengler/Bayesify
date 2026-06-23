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
import type { RubricSummary } from "./api";
import { HeroShell } from "./HeroShell";
import { RubricAbout } from "./RubricAbout";
import { useRubric } from "./rubric";

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
  onGuide: () => void;
  onPrivacy: () => void;
  onCalibration: () => void;
}

export function Landing(p: LandingProps) {
  const canStart = !!p.file || p.identifier.trim().length > 0;
  const rubric = useRubric(p.profile); // full rubric (with step names) for the explainer under the picker
  const rubricOptions = p.rubrics.length ? p.rubrics : [{ id: p.profile, label: p.profile }];

  return (
    <HeroShell
      footer={
        <Box component="footer" sx={{ bgcolor: "background.paper", borderTop: 1, borderColor: "divider" }}>
          <Container maxWidth="lg">
            <Box
              sx={{
                display: "flex",
                flexDirection: { xs: "column", sm: "row" },
                gap: 2,
                justifyContent: "space-between",
                alignItems: { xs: "flex-start", sm: "center" },
                py: 2.5,
              }}
            >
              <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 560 }}>
                Formative report, not a verdict. The badge concept was dropped — Bayesify reports
                per-step practice, not a pass/fail.
              </Typography>
              <Box sx={{ display: "flex", gap: 3 }}>
                <FooterLink onClick={p.onGuide}>Guide</FooterLink>
                <FooterLink onClick={p.onPrivacy}>Privacy</FooterLink>
                <FooterLink onClick={p.onCalibration}>Calibration</FooterLink>
              </Box>
            </Box>
          </Container>
        </Box>
      }
    >
      {/* two columns: pitch | upload panel */}
      <Box
        sx={{
          display: "flex",
          flexDirection: { xs: "column", md: "row" },
          gap: { xs: 4, md: 8 },
          alignItems: { xs: "stretch", md: "center" },
        }}
      >
        <Box sx={{ flex: "1 1 0", minWidth: 0 }}>
          <Typography
            variant="h2"
            sx={{
              fontWeight: 700,
              lineHeight: 1.1,
              letterSpacing: "-0.02em",
              fontSize: { xs: "2rem", sm: "2.5rem", md: "3rem" },
            }}
          >
            How well does this paper follow the Bayesian workflow?
          </Typography>
          <Typography
            sx={{
              mt: 3,
              fontSize: { xs: "1rem", md: "1.125rem" },
              color: "rgba(255,255,255,0.82)",
              maxWidth: 460,
            }}
          >
            Drop a PDF or paste an identifier. You&rsquo;ll get a per-step report with a coverage and
            a quality score — every finding grounded in the paper and in the methodological
            literature.
          </Typography>
        </Box>

        <Box sx={{ flex: "1 1 0", minWidth: 0, width: "100%" }}>
          <UploadPanel {...p} canStart={canStart} rubricOptions={rubricOptions} rubric={rubric} />
        </Box>
      </Box>
    </HeroShell>
  );
}

// The light upload surface that contrasts with the bold hero. It carries the dropzone, the
// identifier fallback, the rubric picker, the mode toggle, and the two actions.
function UploadPanel(
  p: LandingProps & {
    canStart: boolean;
    rubricOptions: { id: string; label: string }[];
    rubric: ReturnType<typeof useRubric>;
  },
) {
  return (
    <Paper
      elevation={0}
      sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3, boxShadow: "0 12px 40px rgba(20, 30, 50, 0.18)" }}
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
      {p.rubric && (
        <Box sx={{ mt: 1 }}>
          <RubricAbout rubric={p.rubric} />
        </Box>
      )}

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
        <ToggleButtonGroup
          exclusive
          size="small"
          value={p.mode}
          onChange={(_, v) => v && p.setMode(v)}
          aria-label="analysis mode"
        >
          <ToggleButton value="full" sx={{ px: 2 }}>
            Full
          </ToggleButton>
          <ToggleButton value="local" sx={{ px: 2 }}>
            Local-only
          </ToggleButton>
        </ToggleButtonGroup>

        <Box sx={{ display: "flex", gap: 1, alignItems: "center", justifyContent: "flex-end" }}>
          <Button
            variant="text"
            size="small"
            disabled={!p.canStart}
            onClick={() => p.onStart("rate")}
            title="Rate this paper yourself against the rubric, blind to the engine's verdict"
          >
            Rate it yourself
          </Button>
          <Button
            variant="contained"
            disableElevation
            disabled={!p.canStart}
            onClick={() => p.onStart("analyze")}
          >
            Analyze
          </Button>
        </Box>
      </Box>
    </Paper>
  );
}

function FooterLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <Link
      component="button"
      type="button"
      underline="hover"
      color="text.secondary"
      onClick={onClick}
      sx={{ fontSize: "0.875rem" }}
    >
      {children}
    </Link>
  );
}
