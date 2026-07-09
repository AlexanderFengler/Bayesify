import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";
import {
  Box,
  Chip,
  CircularProgress,
  Container,
  Divider,
  InputAdornment,
  Link,
  Paper,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import type { Theme } from "@mui/material/styles";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { fetchPapers } from "./api";
import { MathText } from "./MathText";
import { articleUrl, formatByline } from "./paper";
import type { ArchiveFacets, ArchivePaper } from "./types";

const EMPTY_FACETS: ArchiveFacets = { paper_type: [], discipline: [], methods: [], software: [] };
// the facet groups, in render order — key into the facets payload + the paper's own auto-tag arrays.
// `color` is the shared per-category hue (a theme signifier), used for both the filter chips and the
// matching in-card tag chips so a category reads the same colour everywhere.
const GROUPS = [
  { key: "paper_type", label: "Paper type", field: "paper_type", color: "periwinkle" },
  { key: "discipline", label: "Discipline", field: "discipline", color: "aqua" },
  { key: "methods", label: "Methods", field: "methods", color: "violet" },
  { key: "software", label: "Software", field: "software", color: "magenta" },
] as const;

const pretty = (s: string) => s.replace(/[-_]/g, " ");

// The compact uppercase label style, shared by the "Bayesify Score" label and the header chips so
// they read as one family.
const LABEL_FONT = {
  fontSize: "0.72rem",
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
} as const;

// Chip clusters (the top filter facets and the card tags) collapse to this many lines by default,
// hiding the rest behind a "Show more" toggle.
const CHIP_CLAMP_ROWS = 2;

// The categorical-tag chip style, kept in sync with the report page's meta chips (solid, roomy) so a
// tag looks the same on both pages. Colour + filled/outlined variant are set per chip by the caller.
const TAG_CHIP_SX = {
  height: 30,
  fontSize: "0.84rem",
  fontWeight: 600,
  "& .MuiChip-label": { px: 1.25 },
} as const;

// The Archive: every processed paper with its auto tags, searchable by free text + tag facets. Papers
// are tagged automatically (paper type + discipline + methods). Backed by the shared MongoDB reports
// store, so a paper analyzed by anyone shows up here.
export function Archive() {
  const [q, setQ] = useState("");
  // selected facet values per group (AND-filtered server-side)
  const [selected, setSelected] = useState<Record<string, string[]>>({
    paper_type: [],
    discipline: [],
    methods: [],
    software: [],
  });
  const [papers, setPapers] = useState<ArchivePaper[]>([]);
  const [facets, setFacets] = useState<ArchiveFacets>(EMPTY_FACETS);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // two card columns on md+; below that the split collapses to a single in-order stack (a CSS-only
  // collapse of two stacks would read 0,2,4,…,1,3,5)
  const twoCol = useMediaQuery((theme: Theme) => theme.breakpoints.up("md"));

  // debounce the free-text box so we don't refetch on every keystroke
  const [debouncedQ, setDebouncedQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchPapers({
      q: debouncedQ,
      paper_type: selected.paper_type,
      discipline: selected.discipline,
      method: selected.methods,
      software: selected.software,
    })
      .then((r) => {
        if (!alive) return;
        setPapers(r.papers);
        setFacets(r.facets);
        setTotal(r.total);
        setError(null);
      })
      .catch((e) => alive && setError(e.message ?? "could not load the archive"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [debouncedQ, selected]);

  const toggle = (group: string, value: string) =>
    setSelected((cur) => {
      const has = cur[group].includes(value);
      return { ...cur, [group]: has ? cur[group].filter((v) => v !== value) : [...cur[group], value] };
    });

  const activeCount = Object.values(selected).reduce((n, a) => n + a.length, 0);
  const clearAll = () =>
    setSelected({ paper_type: [], discipline: [], methods: [], software: [] });

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            Archive
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 1440 }}>
            Every paper run through Bayesify, tagged automatically by paper type, discipline, and the
            inference methods used, and software detected. Search the text or filter by tags.
          </Typography>
        </Box>
      </Box>

      <TextField
        fullWidth
        size="small"
        placeholder="Search title, authors, or tags…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        sx={{ mt: 3, maxWidth: 1520 }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
              </InputAdornment>
            ),
          },
        }}
      />

      {/* facet filter chips — every group is a column: its label on the shared top row, its chips
          stacked below. Clicking a chip AND-filters the list. */}
      <Box
        sx={{
          mt: 2,
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(4, 1fr)" },
          gap: 2,
          alignItems: "start",
        }}
      >
        {GROUPS.map((g) => {
          const values = facets[g.key as keyof ArchiveFacets];
          if (values.length === 0) return null;
          return (
            <FacetChips
              key={g.key}
              g={g}
              values={values}
              selected={selected[g.key]}
              onToggle={(v) => toggle(g.key, v)}
            />
          );
        })}
      </Box>

      <Box sx={{ mt: 2, display: "flex", alignItems: "center", gap: 2 }}>
        <Typography variant="body2" color="text.secondary">
          {loading ? "Loading…" : `${papers.length} of ${total} paper${total === 1 ? "" : "s"}`}
        </Typography>
        {activeCount > 0 && (
          <Link component="button" type="button" underline="hover" onClick={clearAll} sx={{ fontSize: "0.8rem" }}>
            Clear filters ({activeCount})
          </Link>
        )}
      </Box>

      <Divider sx={{ mt: 1.5 }} />

      {error ? (
        <Typography color="error" sx={{ py: 6 }}>
          {error}
        </Typography>
      ) : loading && papers.length === 0 ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 6 }}>
          <CircularProgress size={20} />
          Loading the archive…
        </Box>
      ) : papers.length === 0 ? (
        <EmptyState hasArchive={total > 0} />
      ) : (
        // two explicit stacks instead of CSS columns: papers alternate left/right in order, so the
        // left column always holds at least as many cards as the right (one more when the count is
        // odd). Each stack flows independently, keeping a constant gap between cards regardless of
        // their variable heights instead of aligning to row peers.
        <Box sx={{ mt: 3, display: "grid", gridTemplateColumns: twoCol ? "1fr 1fr" : "1fr", gap: 2, alignItems: "start" }}>
          {(twoCol ? [papers.filter((_, i) => i % 2 === 0), papers.filter((_, i) => i % 2 === 1)] : [papers]).map(
            (col, ci) => (
              <Box key={ci} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {col.map((p) => (
                  <ArchiveCard key={p.key} p={p} />
                ))}
              </Box>
            ),
          )}
        </Box>
      )}
    </Container>
  );
}

function EmptyState({ hasArchive }: { hasArchive: boolean }) {
  return (
    <Box sx={{ py: 6, color: "text.secondary" }}>
      <Typography sx={{ fontWeight: 600, color: "text.primary" }}>
        {hasArchive ? "No papers match these filters." : "Your archive is empty."}
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.5 }}>
        {hasArchive
          ? "Clear a filter to see more."
          : "Analyze a paper (AI) or rate one (Human) and it will show up here, tagged and searchable."}
      </Typography>
    </Box>
  );
}

// Quality bands for the score medallion — reuse the app's signifier hues (the same green/amber/red
// language the report uses for step status), so a card's colour reads as "how well did it do".
function scoreBand(theme: Theme, q: number): { fg: string; soft: string } {
  const t = theme.tokens;
  if (q >= 0.6) return { fg: t.green, soft: t.greenSoft };
  if (q >= 0.4) return { fg: t.amber, soft: t.amberSoft };
  return { fg: t.red, soft: t.redSoft };
}

// The score in the card header: a two-line "Bayesify / Score" label, right-aligned against the big
// band-coloured number to its right (which spans both label lines). Falls back to a neutral "—" for
// papers without a quality score (e.g. Human ratings that were never graded).
function ScoreBadge({ p }: { p: ArchivePaper }) {
  const theme = useTheme();
  const q = p.quality_score;
  const band = q != null ? scoreBand(theme, q) : null;
  const labelSx = { ...LABEL_FONT, display: "block", lineHeight: 1.2, color: "text.secondary" } as const;

  return (
    <Box sx={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end", textAlign: "right" }}>
      <Typography
        sx={{ fontSize: "2.4rem", fontWeight: 700, lineHeight: 1, color: band ? band.fg : "text.disabled" }}
      >
        {q == null ? "—" : Math.round(q * 100)}
      </Typography>
      <Typography sx={{ ...labelSx, mt: 0.5 }}>Bayesify</Typography>
      <Typography sx={labelSx}>Score</Typography>
    </Box>
  );
}

function ArchiveCard({ p }: { p: ArchivePaper }) {
  const byline = formatByline(p.paper_authors, p.paper_year);
  const url = articleUrl(p.source_label); // the source article, when the paper was submitted by URL

  return (
    <Paper
      variant="outlined"
      sx={{
        position: "relative",
        p: { xs: 2, md: 2.5 },
        borderRadius: 2,
        display: "flex",
        flexDirection: "column",
        transition: "transform .18s ease, box-shadow .18s ease, border-color .18s ease",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: 4,
          borderColor: "primary.main",
        },
      }}
    >
      {/* header: title + author on the left, a vertical divider, then the score on the right (its top
          aligned to the title's top; the divider spans the title+author height). The mode/rubric chips
          sit below, with the steps-covered count after them; "Read paper" (the source article, when
          submitted by URL) sits at that row's right edge — the card's bottom-right corner. The title
          opens the report. */}
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.25 }}>
            {/* stretched link: the ::after overlay covers the whole card, so a click anywhere opens the
                report. Genuinely-interactive children (Read paper, the tag toggles) sit above it via
                z-index and keep their own behaviour. */}
            <Link
              component={RouterLink}
              to={`/paper/${p.paper_id}`}
              color="inherit"
              underline="none"
              sx={{ "&::after": { content: '""', position: "absolute", inset: 0, zIndex: 0 } }}
            >
              <MathText>{p.paper_title ?? p.source_label}</MathText>
            </Link>
          </Typography>
          {byline && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {byline}
            </Typography>
          )}
        </Box>
        <Divider orientation="vertical" flexItem />
        <ScoreBadge p={p} />
      </Box>
      <Divider sx={{my: 1.5}} />
      <Box sx={{ mt: 1, display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center" }}>
        <Chip
          label={p.mode === "full" ? "AI" : "Human"}
          size="small"
          color={p.mode === "full" ? "primary" : "secondary"}
          variant="filled"
          sx={{ height: 20, ...LABEL_FONT }}
        />
        <Chip
          label={pretty(p.rubric_profile)}
          size="small"
          color="slate"
          variant="filled"
          sx={{ height: 20, ...LABEL_FONT }}
        />
        {p.coverage_present != null && p.coverage_applicable != null && (
          <>
            <Divider orientation="vertical" flexItem sx={{ mx: 0.25, my: 0.25 }} />
            <Typography sx={{ ...LABEL_FONT, color: "text.secondary" }}>
              {p.coverage_present}/{p.coverage_applicable} steps covered
            </Typography>
          </>
        )}
        {url && (
          <Link
            href={url}
            target="_blank"
            rel="noreferrer"
            underline="hover"
            sx={{
              ...LABEL_FONT,
              // ml:auto pushes the link to the row's right edge — the card's bottom-right corner
              ml: "auto",
              position: "relative",
              zIndex: 1,
              display: "inline-flex",
              alignItems: "center",
              gap: 0.25,
              color: "primary.main",
            }}
          >
            Read paper
            <OpenInNewIcon sx={{ fontSize: 14 }} />
          </Link>
        )}
      </Box>

    </Paper>
  );
}

// A flex-wrap chip cluster clamped to `rows` lines. When the chips wrap past that height the overflow
// is hidden behind a "Show more"/"Show less" toggle. Shared by the top filter facets (2 lines) and the
// card's paper-type/discipline row (1 line). The overflow is measured (ResizeObserver) against the real
// wrapped height at the current width, so it adapts to the column width rather than guessing by count.
function ClampChips({ children, rows = CHIP_CLAMP_ROWS }: { children: React.ReactNode; rows?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [clampHeight, setClampHeight] = useState<number>();
  const [overflowing, setOverflowing] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const first = el.firstElementChild as HTMLElement | null;
      if (!first) {
        setOverflowing(false);
        return;
      }
      const rowGap = parseFloat(getComputedStyle(el).rowGap) || 0;
      const h = rows * first.offsetHeight + (rows - 1) * rowGap;
      setClampHeight(h);
      setOverflowing(el.scrollHeight > h + 1);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [children, rows]);

  const clamp = overflowing && !expanded;
  return (
    <Box>
      <Box
        ref={ref}
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 0.75,
          overflow: "hidden",
          maxHeight: clamp && clampHeight != null ? `${clampHeight}px` : "none",
        }}
      >
        {children}
      </Box>
      {overflowing && (
        <Link
          component="button"
          type="button"
          underline="hover"
          onClick={() => setExpanded((e) => !e)}
          // position/zIndex keep the toggle clickable above the card's stretched-link overlay
          sx={{ ...LABEL_FONT, mt: 0.75, display: "inline-block", position: "relative", zIndex: 1, color: "text.secondary" }}
        >
          {expanded ? "Show less" : "Show more"}
        </Link>
      )}
    </Box>
  );
}

// One top-filter category: its label plus the (clamped) filter chips. Selected values render filled.
function FacetChips({
  g,
  values,
  selected,
  onToggle,
}: {
  g: (typeof GROUPS)[number];
  values: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const selectedSet = new Set(selected);
  return (
    <Box>
      <Typography sx={{ ...LABEL_FONT, fontSize: "0.7rem", color: "text.secondary" }}>{g.label}</Typography>
      <Box sx={{ mt: 0.75 }}>
        <ClampChips>
          {values.map((v) => (
            <Chip
              key={v}
              label={pretty(v)}
              color={g.color}
              variant={selectedSet.has(v) ? "filled" : "outlined"}
              onClick={() => onToggle(v)}
              sx={TAG_CHIP_SX}
            />
          ))}
        </ClampChips>
      </Box>
    </Box>
  );
}

