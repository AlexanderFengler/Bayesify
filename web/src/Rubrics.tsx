import CheckIcon from "@mui/icons-material/Check";
import StarIcon from "@mui/icons-material/Star";
import {
  Box,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Link,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { useEffect, useState } from "react";
import { fetchRubrics } from "./api";
import { GoldText } from "./GoldText";
import { MathText } from "./MathText";
import { fetchRubric, type Rubric } from "./rubric";
import { SectionHeader, SubsectionTitle } from "./SectionHeader";

// Short column headers for the comparison table, keyed by rubric profile id.
const SHORT_LABEL: Record<string, string> = {
  synthesis: "Synthesis",
  gelman: "Gelman et al.",
  schad: "Schad et al.",
};

// Display order for the rubric columns (and the comparison-table columns, which follow the same list).
const RUBRIC_ORDER = ["gelman", "schad", "synthesis"];
const rubricRank = (profile: string): number => {
  const i = RUBRIC_ORDER.indexOf(profile);
  return i === -1 ? RUBRIC_ORDER.length : i; // unknown profiles sort to the end, stably
};

// Two-line column titles, keyed by rubric profile id: the workflow name on top, its source beneath
// (in a lighter weight). `url`, when present, links the source line to the originating paper. Falls
// back to the rubric's own label when a profile isn't mapped here.
const TITLE: Record<string, { line1: string; line2: React.ReactNode; url?: string }> = {
  synthesis: {
    line1: "Synthesis",
    line2: (
      <>
        Our merged <GoldText>gold standard</GoldText>
      </>
    ),
  },
  gelman: { line1: "Bayesian Workflow", line2: "Gelman et al. (2020)", url: "https://arxiv.org/abs/2011.01808" },
  schad: { line1: "Principled Bayesian Workflow", line2: "Schad et al. (2021)", url: "https://arxiv.org/abs/1904.12765" },
};

// The curated feature matrix: which workflow capabilities each rubric covers. Derived from the three
// rubrics' step sets (synthesis = merged 10-step gold standard with per-step citations; Gelman = the
// full branching workflow incl. multiverse & modeling-as-software; Schad = the pre-data design-analysis
// arc). A checkmark means the rubric has a dedicated step for that capability; a `future` row is a
// planned addition to the Synthesis rubric, marked with a star instead of a check.
const FEATURES: { label: string; has: Record<string, boolean>; future?: boolean }[] = [
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
  // future prospects — planned additions to the Synthesis rubric (starred, not yet a step in any rubric)
  { label: "Amortized workflow", future: true, has: { synthesis: true, gelman: false, schad: false } },
  { label: "Bayes factor workflow", future: true, has: { synthesis: true, gelman: false, schad: false } },
  { label: "Hierarchical modeling", future: true, has: { synthesis: true, gelman: false, schad: false } },
];

// Split the matrix: the shipped capabilities and the starred future prospects render as two tables.
const CURRENT_FEATURES = FEATURES.filter((f) => !f.future);
// const FUTURE_FEATURES = FEATURES.filter((f) => f.future);

// The rubrics reference — a section of the main page (anchored by `id` for the footer nav and every
// rubric mention in the app): the three sets shown side by side, then a comparison table of what
// each one covers.
export function Rubrics({ id }: { id?: string }) {
  const [rubrics, setRubrics] = useState<Rubric[] | null>(null);

  useEffect(() => {
    fetchRubrics()
      .then((list) => Promise.all(list.map((r) => fetchRubric(r.id))))
      .then((loaded) =>
        setRubrics(
          [...loaded].sort(
            (a, b) => rubricRank(a.rubric_profile) - rubricRank(b.rubric_profile),
          ),
        ),
      )
      .catch(() => setRubrics([]));
  }, []);

  return (
    <Container id={id} maxWidth="xl" sx={{ py: { xs: 6, md: 8 } }}>
      <SectionHeader
        title="The rubrics"
        leadMaxWidth={1440}
        lead={
          <>
            Bayesify grades against one of three rubrics. Each decomposes the Bayesian workflow into
            distinct steps. While some workflows are iterative, Bayesify&rsquo;s step-by-step decomposition
            represents the linearized sequence for one cycle. Pick the one whose lens fits your paper or try them all.
          </>
        }
      />

      {!rubrics ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 6 }}>
          <CircularProgress size={20} />
          <Typography>Loading rubrics…</Typography>
        </Box>
      ) : (
        <>
          {/* the three rubrics, side by side. A grid with five shared row bands — header, rule,
              summary, rule, steps — and each column a subgrid spanning them, so the dividers and the
              start of every step list line up across Synthesis / Gelman / Schad regardless of how
              much text each carries. The steps band is 1fr so the columns stay equal height. */}
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" },
              gridTemplateRows: { md: "auto auto auto auto 1fr" },
              columnGap: { md: 3 },
              rowGap: { xs: 2.5, md: 0 },
              alignItems: "stretch",
            }}
          >
            {rubrics.map((r) => (
              <RubricColumn key={r.rubric_profile} rubric={r} />
            ))}
          </Box>

          <Divider sx={{ my: { xs: 5, md: 7 } }} />

          {/* the comparison — the shipped capabilities, then the roadmap. Subsection headings sit on
              the same tier as the guide's flow titles so the whole page reads one scale. */}
          <SubsectionTitle>How they differ</SubsectionTitle>
          {/* subsection captions run full width on the 0.95rem caption tier (matching the guide's) */}
          <Typography color="text.secondary" sx={{ mt: 0.75, mb: 3, fontSize: "0.95rem", lineHeight: 1.6 }}>
            Each rubric encompasses slightly different steps.
          </Typography>
          <ComparisonTable columns={rubrics.map((r) => r.rubric_profile)} rows={CURRENT_FEATURES} />

          <SubsectionTitle sx={{ mt: { xs: 5, md: 7 } }}>On the roadmap</SubsectionTitle>
          <Typography color="text.secondary" sx={{ mt: 0.75, fontSize: "0.95rem", lineHeight: 1.6 }}>
            Capabilities planned for the Synthesis rubric: amortized workflow, Bayes factor workflow, and hierarchical modeling. Stay tuned!
          </Typography>
        </>
      )}
    </Container>
  );
}

function RubricColumn({ rubric }: { rubric: Rubric }) {
  const title = TITLE[rubric.rubric_profile];
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2.5, md: 3 },
        borderRadius: 3,
        minWidth: 0,
        // span the five shared row bands as a subgrid so every column's bands line up
        gridRow: { md: "1 / -1" },
        display: { xs: "flex", md: "grid" },
        flexDirection: "column",
        gridTemplateRows: { md: "subgrid" },
        // a cool, responsive lift on hover — the card brightens, lifts, and casts a primary-tinted glow
        transition: "transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease",
        "&:hover": {
          transform: { md: "translateY(-6px)" },
          borderColor: "primary.main",
          boxShadow: (t) => `0 14px 36px ${alpha(t.palette.primary.main, 0.22)}`,
        },
      }}
    >
      {/* header: workflow name + source on the left, step-count chip in the top-right corner aligned
          to the title's top — so the chip sits at the band's height, not stacked below the title */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
            {title?.line1 ?? rubric.label}
          </Typography>
          {title && (
            <Typography sx={{ fontWeight: 400, fontSize: "0.95rem", color: "text.secondary", lineHeight: 1.25, mt: 0.25 }}>
              {title.url ? (
                <Link href={title.url} target="_blank" rel="noreferrer" underline="hover" color="inherit">
                  {title.line2}
                </Link>
              ) : (
                title.line2
              )}
            </Typography>
          )}
        </Box>
        <Chip size="small" label={`${rubric.steps.length} steps`} sx={{ flexShrink: 0 }} />
      </Box>

      <Divider sx={{ my: 2 }} />

      <Typography variant="body2" color="text.secondary">
        <MathText>{rubric.summary}</MathText>
      </Typography>

      <Divider sx={{ my: 2 }} />

      {/* steps outline grows to fill, so the three columns stay equal height */}
      <Box
        component="ol"
        sx={{ listStyle: "none", p: 0, m: 0, display: "flex", flexDirection: "column", gap: 1 }}
      >
        {rubric.steps.map((s) => (
          <Box component="li" key={s.id} sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
            <Typography
              component="span"
              sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 12, fontWeight: 600, color: "text.disabled", flexShrink: 0 }}
            >
              {s.id}
            </Typography>
            <Typography component="span" sx={{ fontSize: "0.95rem" }}>
              {s.name}
            </Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

function ComparisonTable({ columns, rows }: { columns: string[]; rows: typeof FEATURES }) {
  return (
    // No surrounding box — the table sits directly on the aurora. A strong header rule, hairline row
    // separators and a soft row hover do the structural work the border used to.
    <TableContainer sx={{ overflowX: "auto" }}>
      <Table
        sx={{
          "& th, & td": { borderBottom: "1px solid", borderColor: "divider", py: 1.5 },
          "& tbody tr:last-of-type td": { borderBottom: 0 },
          "& tbody tr": { transition: "background-color 120ms" },
          "& tbody tr:hover": { bgcolor: "action.hover" },
        }}
      >
        <TableHead>
          <TableRow
            sx={{
              "& th": {
                fontWeight: 700,
                color: "text.primary",
                borderBottomWidth: 2,
                borderColor: (t) => t.tokens.lineStrong,
              },
            }}
          >
            <TableCell sx={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Capability
            </TableCell>
            {columns.map((c) => (
              <TableCell key={c} align="center" sx={{ width: 132 }}>
                {SHORT_LABEL[c] ?? c}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((f) => (
            <TableRow key={f.label} hover>
              <TableCell sx={{ color: "text.primary" }}>{f.label}</TableCell>
              {columns.map((c) => (
                <TableCell key={c} align="center">
                  {f.has[c] ? (
                    // a solid dot with the mark knocked out in the page-background colour: a green tick
                    // for a shipped capability, a blue star for a planned (future-prospect) one
                    <Box
                      sx={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 24,
                        height: 24,
                        borderRadius: "50%",
                        bgcolor: f.future ? "#6969ff" : "success.main",
                      }}
                    >
                      {f.future ? (
                        <StarIcon sx={{ fontSize: 16, color: (t) => t.tokens.aurora.base }} aria-label="planned" />
                      ) : (
                        <CheckIcon sx={{ fontSize: 16, color: (t) => t.tokens.aurora.base }} aria-label="yes" />
                      )}
                    </Box>
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
