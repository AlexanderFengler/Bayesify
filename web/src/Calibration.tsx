import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
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
import { type CalibrationReport, getCalibration, type MetricStat, type TierCCase } from "./api";

// Width-constrained shell shared by every state of the calibration view (loading / error / report),
// so the column width stays constant. The header is permanent (Layout) and lives above this.
function CalibrationShell({ children }: { children: React.ReactNode }) {
  return (
    <Container maxWidth="md" sx={{ py: { xs: 3, md: 5 } }}>
      {children}
    </Container>
  );
}

// A small-caps section label, matching the "grounding-label" used across the migrated screens.
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="caption"
      sx={{ fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: "0.06em" }}
    >
      {children}
    </Typography>
  );
}

// The full calibration view: it renders the validation report the harness produced — honestly. The
// status drives a per-state banner; the demo state gets a loud, non-dismissable FAKE-DATA banner so
// fabricated numbers can never be mistaken for a real measurement.
export function Calibration({ onExit }: { onExit: () => void }) {
  const [rep, setRep] = useState<CalibrationReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getCalibration()
      .then(setRep)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  if (err) {
    return (
      <CalibrationShell>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={onExit}>
              Back
            </Button>
          }
        >
          <AlertTitle>Couldn&rsquo;t load calibration</AlertTitle>
          {err}
        </Alert>
      </CalibrationShell>
    );
  }
  if (!rep) {
    return (
      <CalibrationShell>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 6 }}>
          <CircularProgress size={20} />
          <Typography>Loading calibration…</Typography>
        </Box>
      </CalibrationShell>
    );
  }

  return (
    <CalibrationShell>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.08em" }}>
            Calibration
          </Typography>
          <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
            Engine vs. expert agreement
          </Typography>
        </Box>
        <Button variant="outlined" onClick={onExit} sx={{ flexShrink: 0 }}>
          Back
        </Button>
      </Box>

      <Box sx={{ mt: 2.5 }}>
        <StatusBanner rep={rep} />
      </Box>

      {rep.status === "not_yet_validated" ? (
        <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3, mt: 2.5 }}>
          <Typography color="text.secondary">
            {rep.note ??
              "No validation has run yet. Coverage and quality scores are produced, but they have " +
                "not been checked against expert ratings."}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Until the validation run (M7) reports agreement metrics, treat every report as{" "}
            <strong>formative, not a verdict</strong>.
          </Typography>
        </Paper>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5, mt: 2.5 }}>
          <MetaLine rep={rep} />
          <Metrics rep={rep} />
          {rep.confusion && <Confusion table={rep.confusion} />}
          {rep.tier_c_cases && rep.tier_c_cases.length > 0 && <TierCCases cases={rep.tier_c_cases} />}
          <Caveats caveats={rep.validity_caveats ?? []} />
        </Box>
      )}
    </CalibrationShell>
  );
}

function StatusBanner({ rep }: { rep: CalibrationReport }) {
  if (rep.status === "demo_fake_data") {
    return (
      <Alert severity="error" variant="filled">
        <AlertTitle>⚠️ FAKE DATA — plumbing demonstration, not a measurement.</AlertTitle>
        Every number below is computed from fabricated reports so the page can be built and critiqued
        before real expert ratings exist. It is <strong>not</strong> the engine&rsquo;s accuracy.
      </Alert>
    );
  }
  if (rep.status === "development_set") {
    return (
      <Alert severity="warning">
        <AlertTitle>Development-set agreement.</AlertTitle>
        Measured against the gold set the engine is tuned on — not held-out accuracy. Every number is
        labelled &ldquo;development-set agreement.&rdquo;
      </Alert>
    );
  }
  if (rep.status === "holdout") {
    return (
      <Alert severity="success">
        <AlertTitle>Held-out accuracy.</AlertTitle>
        Measured on a sealed holdout the engine never saw.
      </Alert>
    );
  }
  return (
    <Alert severity="info">
      <strong>Not yet validated.</strong>
    </Alert>
  );
}

function MetaLine({ rep }: { rep: CalibrationReport }) {
  const raters = Object.entries(rep.rater_relationships ?? {})
    .map(([k, v]) => `${v} ${k}`)
    .join(", ");
  return (
    <Box>
      <Typography variant="body2">
        <strong>{rep.n_papers ?? 0}</strong> papers
        {rep.n_excluded ? ` (${rep.n_excluded} excluded)` : ""} ·{" "}
        {Object.entries(rep.tier_counts ?? {})
          .map(([t, n]) => `tier ${t}: ${n}`)
          .join(", ")}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        engine {rep.engine_version} · rubric {rep.rubric_version} · {rep.rubric_profile} profile
        {raters && ` · raters: ${raters}`}
      </Typography>
      {rep.domain_note && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          {rep.domain_note}
        </Typography>
      )}
    </Box>
  );
}

function fmt(s: MetricStat): string {
  if (s.value === null || s.value === undefined) return "—";
  let body = s.value.toFixed(2);
  if (s.x !== undefined) body += ` (${s.x}/${s.n})`;
  if (s.ci_lo !== null && s.ci_hi !== null) body += ` [${s.ci_lo.toFixed(2)}, ${s.ci_hi.toFixed(2)}]`;
  return body;
}

function Metric({ s }: { s?: MetricStat }) {
  if (!s) return null;
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: 2,
        py: 0.75,
        borderBottom: 1,
        borderColor: "divider",
        opacity: s.preliminary ? 0.7 : 1,
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {s.label}
      </Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="body2" sx={{ fontFamily: (t) => t.tokens.mono, fontWeight: 600 }}>
          {fmt(s)}
        </Typography>
        {s.preliminary && s.value !== null && (
          <Chip size="small" label="preliminary" title="n below the minimum-data floor" />
        )}
      </Box>
    </Box>
  );
}

function Metrics({ rep }: { rep: CalibrationReport }) {
  const order: (MetricStat | undefined)[] = [
    rep.applicability_kappa,
    rep.status_kappa,
    rep.status_percent_agreement,
    rep.status_ac1,
    rep.inter_expert_status_kappa,
    rep.test_retest_kappa,
    rep.absence_fpr_strict,
    rep.absence_fpr_broad,
    rep.absence_miss_rate,
    rep.coverage_icc,
    rep.quality_icc,
    rep.relevance_sensitivity,
    rep.relevance_specificity,
    rep.paper_class_accuracy,
  ];
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3 }}>
      <SectionLabel>Agreement metrics</SectionLabel>
      <Box sx={{ mt: 1 }}>
        {order.map((s, i) => (
          <Metric key={i} s={s} />
        ))}
      </Box>
    </Paper>
  );
}

function Confusion({ table }: { table: Record<string, Record<string, number>> }) {
  const rows = Object.keys(table);
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(table[r]))));
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3 }}>
      <SectionLabel>Status confusion (rows = consensus, cols = engine)</SectionLabel>
      <TableContainer sx={{ mt: 1 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell />
              {cols.map((c) => (
                <TableCell key={c} align="right">
                  {c}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r}>
                <TableCell component="th" sx={{ fontWeight: 600 }}>
                  {r}
                </TableCell>
                {cols.map((c) => (
                  <TableCell key={c} align="right">
                    {table[r][c] ?? 0}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

function TierCCases({ cases }: { cases: TierCCase[] }) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3 }}>
      <SectionLabel>
        Tier-C special cases — reported individually (too few to pool into a rate)
      </SectionLabel>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5, mt: 1.5 }}>
        {cases.map((c) => (
          <Box key={c.work_id}>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap", mb: 1 }}>
              <Typography sx={{ fontWeight: 700 }}>{c.work_id}</Typography>
              <Typography variant="caption" color="text.secondary">
                relevance: consensus <code>{c.relevance_consensus}</code> / engine{" "}
                <code>{c.relevance_engine}</code>
              </Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>step</TableCell>
                    <TableCell>consensus</TableCell>
                    <TableCell>engine</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {c.steps.map((s) => (
                    <TableRow key={s.step_id} sx={!s.agree ? { bgcolor: "error.light" } : undefined}>
                      <TableCell component="th" sx={{ fontWeight: 600 }}>
                        {s.step_id}
                      </TableCell>
                      <TableCell>
                        <code>{s.consensus}</code>
                      </TableCell>
                      <TableCell>
                        <code>{s.engine}</code>
                      </TableCell>
                      <TableCell>{s.agree ? "✓" : "✗"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

function Caveats({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3 }}>
      <SectionLabel>Read this carefully</SectionLabel>
      <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2.5, display: "flex", flexDirection: "column", gap: 0.75 }}>
        {caveats.map((c, i) => (
          <Typography component="li" variant="body2" color="text.secondary" key={i}>
            {c}
          </Typography>
        ))}
      </Box>
    </Paper>
  );
}
