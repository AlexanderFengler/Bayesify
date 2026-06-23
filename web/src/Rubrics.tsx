import CheckIcon from "@mui/icons-material/Check";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { fetchRubrics } from "./api";
import { fetchRubric, type Rubric } from "./rubric";

// Short column headers for the comparison table, keyed by rubric profile id.
const SHORT_LABEL: Record<string, string> = {
  synthesis: "Synthesis",
  gelman: "Gelman",
  schad: "Schad",
};

// The curated feature matrix: which workflow capabilities each rubric covers. Derived from the three
// rubrics' step sets (synthesis = merged 10-step gold standard with per-step citations; Gelman = the
// full branching workflow incl. multiverse & modeling-as-software; Schad = the pre-data design-analysis
// arc). A checkmark means the rubric has a dedicated step for that capability.
const FEATURES: { label: string; has: Record<string, boolean> }[] = [
  { label: "Model specification & justification", has: { synthesis: true, gelman: true, schad: true } },
  { label: "Prior specification", has: { synthesis: true, gelman: true, schad: true } },
  { label: "Prior predictive checks", has: { synthesis: true, gelman: true, schad: true } },
  { label: "Pre-data design analysis (before data)", has: { synthesis: false, gelman: false, schad: true } },
  { label: "Simulation-based calibration (SBC)", has: { synthesis: true, gelman: true, schad: true } },
  { label: "Model sensitivity / parameter recovery", has: { synthesis: true, gelman: false, schad: true } },
  { label: "Convergence & sampling diagnostics", has: { synthesis: true, gelman: true, schad: true } },
  { label: "Addressing computational problems", has: { synthesis: false, gelman: true, schad: false } },
  { label: "Posterior predictive checks", has: { synthesis: true, gelman: true, schad: true } },
  { label: "Cross-validation & influence (LOO)", has: { synthesis: true, gelman: true, schad: false } },
  { label: "Model comparison / selection", has: { synthesis: true, gelman: true, schad: false } },
  { label: "Iterative model expansion (multiverse)", has: { synthesis: false, gelman: true, schad: false } },
  { label: "Reporting & reproducibility", has: { synthesis: true, gelman: true, schad: false } },
  { label: "Posterior summary & inference communication", has: { synthesis: true, gelman: false, schad: true } },
  { label: "Per-step source citations", has: { synthesis: true, gelman: false, schad: false } },
];

// The dedicated reference page for the rubrics: the three sets shown side by side, then a comparison
// table of what each one covers. Linked from the footer and from every rubric mention in the app.
export function Rubrics({ onExit }: { onExit: () => void }) {
  const [rubrics, setRubrics] = useState<Rubric[] | null>(null);

  useEffect(() => {
    fetchRubrics()
      .then((list) => Promise.all(list.map((r) => fetchRubric(r.id))))
      .then(setRubrics)
      .catch(() => setRubrics([]));
  }, []);

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 3, md: 5 } }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.08em" }}>
            Reference
          </Typography>
          <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
            The rubrics
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 720 }}>
            Bayesify grades against one of three rubrics. Each decomposes the Bayesian workflow into
            named steps; pick the one whose lens fits your paper.
          </Typography>
        </Box>
        <Button variant="outlined" onClick={onExit} sx={{ flexShrink: 0 }}>
          Back
        </Button>
      </Box>

      {!rubrics ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 6 }}>
          <CircularProgress size={20} />
          <Typography>Loading rubrics…</Typography>
        </Box>
      ) : (
        <>
          {/* the three rubrics, side by side */}
          <Box
            sx={{
              mt: 3,
              display: "flex",
              flexDirection: { xs: "column", md: "row" },
              gap: { xs: 2.5, md: 3 },
              alignItems: "stretch",
            }}
          >
            {rubrics.map((r) => (
              <RubricColumn key={r.rubric_profile} rubric={r} />
            ))}
          </Box>

          <Divider sx={{ my: { xs: 4, md: 5 } }} />

          {/* the comparison */}
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5 }}>
            How they differ
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Which workflow capabilities each rubric has a dedicated step for.
          </Typography>
          <ComparisonTable columns={rubrics.map((r) => r.rubric_profile)} />
        </>
      )}
    </Container>
  );
}

function RubricColumn({ rubric }: { rubric: Rubric }) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3, flex: "1 1 0", minWidth: 0 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
        {rubric.label}
      </Typography>
      <Chip size="small" label={`${rubric.steps.length} steps`} sx={{ mt: 1 }} />
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
        {rubric.summary}
      </Typography>
      <Box component="ol" sx={{ listStyle: "none", p: 0, m: 0, mt: 2, display: "flex", flexDirection: "column", gap: 1 }}>
        {rubric.steps.map((s) => (
          <Box component="li" key={s.id} sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
            <Typography
              component="span"
              sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 12, fontWeight: 600, color: "text.disabled", flexShrink: 0 }}
            >
              {s.id}
            </Typography>
            <Typography component="span" variant="body2">
              {s.name}
            </Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

function ComparisonTable({ columns }: { columns: string[] }) {
  return (
    <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 3 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 700 }}>Capability</TableCell>
            {columns.map((c) => (
              <TableCell key={c} align="center" sx={{ fontWeight: 700 }}>
                {SHORT_LABEL[c] ?? c}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {FEATURES.map((f) => (
            <TableRow key={f.label} hover>
              <TableCell sx={{ color: "text.secondary" }}>{f.label}</TableCell>
              {columns.map((c) => (
                <TableCell key={c} align="center">
                  {f.has[c] ? (
                    <CheckIcon fontSize="small" color="success" aria-label="yes" />
                  ) : (
                    <Box component="span" sx={{ color: "text.disabled" }} aria-label="no">
                      —
                    </Box>
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
