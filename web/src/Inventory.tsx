import FormatQuoteIcon from "@mui/icons-material/FormatQuote";
import { Box, Button, Chip, Container, Link, Typography } from "@mui/material";
import type { EvidenceInventory, InventoryFamily, InventoryHit, PaperState } from "./types";

const FAMILY_NAMES: Record<string, string> = {
  software: "Software & tooling",
  method: "Bayesian methods",
  diagnostic: "Diagnostics",
  workflow: "Workflow signals",
  sampler: "Sampler configuration",
  open_science: "Open science",
};

// A friendlier label for a detector id (e.g. "software.stan" -> "stan").
function shortId(id: string): string {
  const dot = id.indexOf(".");
  return dot === -1 ? id : id.slice(dot + 1);
}

function valueText(value: Record<string, unknown> | null): string | null {
  if (!value) return null;
  const metric = value.metric as string | undefined;
  if (value.op != null && value.value != null) return `${metric} ${value.op} ${value.value}`;
  if (value.count != null) return `${metric}: ${value.count}`;
  return Object.entries(value)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
}

// The local-only detection inventory, given the same full-bleed MUI treatment as the report: the
// shared top bar, a sticky left summary column, and de-carded family sections on the right.
export function Inventory({
  paper,
  onReset,
  onRate,
}: {
  paper: PaperState;
  onReset: () => void;
  onRate: (paperId: string) => void;
}) {
  const inv = paper.inventory!;
  const families = inv.families.filter((f) => f.found.length > 0 || f.not_detected.length > 0);
  return (
    <Container maxWidth="lg" sx={{ py: { xs: 3, md: 5 } }}>
      <Box
        sx={{
          display: "flex",
          flexDirection: { xs: "column", md: "row" },
          gap: { xs: 4, md: 6 },
          alignItems: "flex-start",
        }}
      >
        {/* LEFT: detection summary + where the engine looked */}
        <Box sx={{ flex: { md: "0 0 38%" }, width: "100%", position: { md: "sticky" }, top: { md: 88 } }}>
          <SummaryColumn paper={paper} inv={inv} onReset={onReset} onRate={onRate} />
        </Box>

        {/* RIGHT: the detections, by family */}
        <Box sx={{ flex: "1 1 0", width: "100%", minWidth: 0 }}>
          <Typography variant="overline" color="text.secondary">
            Detections by family
          </Typography>
          <Box sx={{ mt: 1, display: "flex", flexDirection: "column", gap: 3 }}>
            {families.map((f) => (
              <FamilySection key={f.family} f={f} />
            ))}
          </Box>
        </Box>
      </Box>
    </Container>
  );
}

function SummaryColumn({
  paper,
  inv,
  onReset,
  onRate,
}: {
  paper: PaperState;
  inv: EvidenceInventory;
  onReset: () => void;
  onRate: (paperId: string) => void;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
      <Box>
        <Chip size="small" variant="outlined" color="success" label="Local-only · detection mode" sx={{ mb: 1 }} />
        <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
          {paper.source_label}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 1.5, flexWrap: "wrap" }}>
          {/* Blind entry: rate from the no-grade detection view, never from the engine's report. */}
          <Button size="small" variant="contained" disableElevation onClick={() => onRate(paper.paper_id)}>
            Rate this paper (blind)
          </Button>
          <Button size="small" variant="outlined" onClick={onReset}>
            Analyze another
          </Button>
        </Box>
      </Box>

      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
        <Typography sx={{ fontSize: "2.5rem", fontWeight: 700, lineHeight: 1, color: "primary.main" }}>
          {inv.n_hits}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          signals detected
        </Typography>
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
        <Typography variant="body2" color="text.secondary">
          parsed with <strong>{paper.parser ?? "—"}</strong> · {inv.where_looked.length} sections scanned
        </Typography>
        <Typography variant="caption" sx={{ color: "success.main", fontWeight: 600 }}>
          No LLM · nothing left this machine.
        </Typography>
        <Box sx={{ display: "flex", gap: 1.5, mt: 0.5 }}>
          <Link href={`/api/papers/${paper.paper_id}/report.json`} target="_blank" rel="noreferrer" variant="body2">
            report.json
          </Link>
          <Link href={`/api/papers/${paper.paper_id}/report.md`} target="_blank" rel="noreferrer" variant="body2">
            report.md
          </Link>
        </Box>
      </Box>

      <Typography variant="body2" color="text.secondary">
        This is a <strong>detection inventory</strong>, not a graded assessment. Detectors find signals
        and show exactly where; they don&rsquo;t judge whether a practice was done <em>well</em> — that&rsquo;s
        the full (LLM) report&rsquo;s job. Absences mean <em>not detected</em>, never &ldquo;not done.&rdquo;
      </Typography>

      <WhereLooked inv={inv} />
    </Box>
  );
}

function FamilySection({ f }: { f: InventoryFamily }) {
  return (
    <Box component="section">
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 1 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          {FAMILY_NAMES[f.family] ?? f.family}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {f.found.length} found
        </Typography>
      </Box>

      {f.found.length > 0 ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          {f.found.map((h, i) => (
            <Hit key={i} h={h} />
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          Nothing in this family detected.
        </Typography>
      )}

      {f.not_detected.length > 0 && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: "0.04em" }}>
            not detected
          </Typography>
          {f.not_detected.map((id) => (
            <Chip key={id} size="small" variant="outlined" label={shortId(id)} sx={{ color: "text.secondary" }} />
          ))}
        </Box>
      )}
    </Box>
  );
}

function Hit({ h }: { h: InventoryHit }) {
  const v = valueText(h.value);
  return (
    <Box sx={{ pl: 2, borderLeft: "3px solid", borderColor: "divider" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography component="span" sx={{ fontWeight: 700, fontFamily: (t) => t.tokens.mono, fontSize: "0.85rem" }}>
          {shortId(h.detector_id)}
        </Typography>
        {v && (
          <Typography component="span" variant="caption" sx={{ color: "primary.main", fontFamily: (t) => t.tokens.mono }}>
            {v}
          </Typography>
        )}
      </Box>
      <Typography variant="body2" sx={{ display: "flex", gap: 0.5, mt: 0.25 }}>
        <FormatQuoteIcon sx={{ fontSize: 16, color: "text.disabled", flex: "0 0 auto", mt: "2px" }} />
        <span>
          {h.quote}
          <Box component="span" sx={{ display: "block", color: "text.secondary", fontSize: "0.75rem", mt: 0.25 }}>
            {h.section_title || h.section_id}
            {h.page != null && `, p.${h.page}`}
          </Box>
        </span>
      </Typography>
    </Box>
  );
}

// The local-mode "nothing detected / not run" notice, given the same full-bleed treatment.
export function LocalNotice({
  notice,
  source,
  onReset,
}: {
  notice: string;
  source: string;
  onReset: () => void;
}) {
  return (
    <Container maxWidth="md" sx={{ py: { xs: 4, md: 6 } }}>
      <Chip size="small" variant="outlined" label="No analysis run yet" sx={{ mb: 1.5 }} />
      <Typography variant="h5" sx={{ fontWeight: 700 }}>
        {source}
      </Typography>
      <Typography sx={{ mt: 1.5, color: "text.secondary" }}>{notice}</Typography>
      <Button variant="contained" disableElevation onClick={onReset} sx={{ mt: 3 }}>
        Analyze another
      </Button>
    </Container>
  );
}

function WhereLooked({ inv }: { inv: EvidenceInventory }) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        Where the engine looked
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
        {inv.where_looked.map((s) => (
          <Chip
            key={s.section_id}
            size="small"
            variant="outlined"
            label={s.title || s.kind}
            title={`${s.kind} · ${s.section_id}`}
          />
        ))}
      </Box>
      {inv.skipped.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          Not scanned (a precision trap — reference lists name tools the paper doesn&rsquo;t use):{" "}
          {inv.skipped.map((s) => s.title || s.kind).join(", ")}.
        </Typography>
      )}
    </Box>
  );
}
