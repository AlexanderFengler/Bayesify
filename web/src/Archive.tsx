import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FirstPageIcon from "@mui/icons-material/FirstPage";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import LastPageIcon from "@mui/icons-material/LastPage";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";
import {
  Box,
  Chip,
  CircularProgress,
  Container,
  Divider,
  IconButton,
  InputAdornment,
  Link,
  MenuItem,
  Paper,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import type { Theme } from "@mui/material/styles";
import { Children, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { fetchPapers } from "./api";
import { MathText } from "./MathText";
import { articleUrl, formatByline } from "./paper";
import type { ArchiveFacets, ArchivePaper } from "./types";

const EMPTY_FACETS: ArchiveFacets = { paper_type: [], discipline: [], methods: [], software: [] };
// the facet groups, in render order — key into the facets payload + the paper's own auto-tag arrays.
// `color` is the shared per-category hue (a theme signifier), used for both the filter chips and the
// matching in-card tag chips so a category reads the same color everywhere.
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

// Chip clusters (the top filter facets) collapse to this many lines by default, with the rest behind a
// circular expand arrow that sits inline right after the last visible chip.
const CHIP_CLAMP_ROWS = 2;

// The inline expand/collapse arrow on a clamped chip cluster is a circle this size (matching the chip
// height in TAG_CHIP_SX), so it reads as one more chip on the row.
const CHIP_TOGGLE_SIZE = 30;

// The archive list is paginated to keep it scannable as the corpus grows; each page holds this many
// papers and slides in horizontally when the page changes (see PaperGrid).
const PER_PAGE = 10;

// How the list can be ordered (client-side). "Score" is the default — the archive is primarily a
// leaderboard of how well papers did. Each key maps to a per-paper sort value in `sortValue`; every
// sort is descending with missing values sorted last.
type SortKey = "recent" | "year" | "score" | "coverage";
const SORTS: { key: SortKey; label: string }[] = [
  { key: "recent", label: "Latest scored" },
  { key: "year", label: "Publication year" },
  { key: "score", label: "Score" },
  { key: "coverage", label: "Coverage" },
];

function sortValue(p: ArchivePaper, key: SortKey): number | null {
  switch (key) {
    case "recent":
      return Date.parse(p.updated_at) || null;
    case "year":
      return p.paper_year;
    case "score":
      return p.quality_score;
    case "coverage":
      return p.coverage_present != null && p.coverage_applicable
        ? p.coverage_present / p.coverage_applicable
        : null;
  }
}

// Approximate height of the two-line clamped title (h6 ≈ 1.25rem × 1.25 line-height × 2 lines) — used
// only to size the box that vertically centers the expand control against those two lines. The title's
// own reservation is done in em (see ArchiveTitle) so it's exact; this just needs to be close.
const TITLE_BLOCK_HEIGHT = "3.125rem";

// The categorical-tag chip style, kept in sync with the report page's meta chips (solid, roomy) so a
// tag looks the same on both pages. Color + filled/outlined variant are set per chip by the caller.
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
  // selected facet values per group (server-side: OR within a group, AND across groups)
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
  // client-side pagination: which page (0-based) is showing, and which way the next page should slide
  // in ("left" when advancing, "right" when going back) so the swipe direction matches the navigation.
  const [page, setPage] = useState(0);
  const [slideDir, setSlideDir] = useState<"left" | "right">("left");
  const [sort, setSort] = useState<SortKey>("score");
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

  // a new search, filter set, or sort order reshuffles the list — always land back on the first page
  // rather than a now-out-of-range one.
  useEffect(() => {
    setPage(0);
  }, [debouncedQ, selected, sort]);

  const sortedPapers = useMemo(() => {
    return [...papers].sort((a, b) => {
      const va = sortValue(a, sort);
      const vb = sortValue(b, sort);
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // missing values sort last
      if (vb == null) return -1;
      return vb - va; // descending
    });
  }, [papers, sort]);

  const pageCount = Math.max(1, Math.ceil(sortedPapers.length / PER_PAGE));
  const pagePapers = sortedPapers.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE);
  const visibleStart = sortedPapers.length === 0 ? 0 : page * PER_PAGE + 1;
  const visibleEnd = Math.min((page + 1) * PER_PAGE, sortedPapers.length);
  const visibleCountLabel =
    visibleStart === visibleEnd
      ? `${visibleStart} of ${total}`
      : `${visibleStart}-${visibleEnd} of ${total}`;
  const goToPage = (next: number) => {
    setSlideDir(next > page ? "left" : "right");
    setPage(next);
  };

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
          stacked below. Chips within a group OR together; groups AND across. */}
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

      <Box sx={{ mt: 2, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography variant="body2" color="text.secondary">
          {loading ? "Loading…" : `${visibleCountLabel} paper${total === 1 ? "" : "s"}`}
        </Typography>
        {pageCount > 1 && <Pager page={page} pageCount={pageCount} onGoTo={goToPage} />}
        {activeCount > 0 && (
          <Link component="button" type="button" underline="hover" onClick={clearAll} sx={{ fontSize: "0.8rem" }}>
            Clear filters ({activeCount})
          </Link>
        )}
        {/* a compact, label-less pill so it sits on the row like the chips and pager rather than a
            full-height form field: a quiet "Sort" prefix, the value in the chip's weight/size */}
        <TextField
          select
          size="small"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          slotProps={{
            input: {
              startAdornment: (
                <Typography
                  component="span"
                  sx={{ ...LABEL_FONT, fontSize: "0.66rem", color: "text.secondary", mr: 0.75, whiteSpace: "nowrap" }}
                >
                  Sort
                </Typography>
              ),
            },
          }}
          sx={{
            ml: "auto",
            "& .MuiOutlinedInput-root": { borderRadius: 999, height: 32, pl: 1.5 },
            "& .MuiSelect-select": {
              display: "flex",
              alignItems: "center",
              py: 0,
              pl: 0,
              fontSize: "0.84rem",
              fontWeight: 600,
            },
          }}
        >
          {SORTS.map((s) => (
            <MenuItem key={s.key} value={s.key} sx={{ fontSize: "0.84rem" }}>
              {s.label}
            </MenuItem>
          ))}
        </TextField>
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
        <PaperGrid papers={pagePapers} twoCol={twoCol} page={page} slideDir={slideDir} />
      )}
    </Container>
  );
}

// The compact page navigator that sits on the count row: first / previous, the highlighted current
// page over the total, then next / last. Buttons disable at the ends.
function Pager({ page, pageCount, onGoTo }: { page: number; pageCount: number; onGoTo: (next: number) => void }) {
  const atStart = page === 0;
  const atEnd = page === pageCount - 1;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.25 }}>
      <IconButton size="small" aria-label="First page" disabled={atStart} onClick={() => onGoTo(0)}>
        <FirstPageIcon fontSize="small" />
      </IconButton>
      <IconButton size="small" aria-label="Previous page" disabled={atStart} onClick={() => onGoTo(page - 1)}>
        <ChevronLeftIcon fontSize="small" />
      </IconButton>
      <Typography variant="body2" sx={{ mx: 0.5, color: "text.secondary", whiteSpace: "nowrap" }}>
        <Box
          component="span"
          sx={{
            display: "inline-block",
            minWidth: 24,
            textAlign: "center",
            px: 0.75,
            py: 0.25,
            borderRadius: 1,
            fontWeight: 700,
            bgcolor: "primary.main",
            color: "primary.contrastText",
          }}
        >
          {page + 1}
        </Box>{" "}
        / {pageCount}
      </Typography>
      <IconButton size="small" aria-label="Next page" disabled={atEnd} onClick={() => onGoTo(page + 1)}>
        <ChevronRightIcon fontSize="small" />
      </IconButton>
      <IconButton size="small" aria-label="Last page" disabled={atEnd} onClick={() => onGoTo(pageCount - 1)}>
        <LastPageIcon fontSize="small" />
      </IconButton>
    </Box>
  );
}

// One page of the archive list. The cards are laid out as two explicit stacks instead of CSS columns:
// papers alternate left/right in order, so the left column always holds at least as many cards as the
// right (one more when the count is odd). Each stack flows independently, keeping a constant gap
// between cards regardless of their variable heights instead of aligning to row peers. The whole grid
// is keyed by page and re-mounts on a page change, sliding in from the side navigation came from — a
// swipe: forward pages enter from the right, back pages from the left.
function PaperGrid({
  papers,
  twoCol,
  page,
  slideDir,
}: {
  papers: ArchivePaper[];
  twoCol: boolean;
  page: number;
  slideDir: "left" | "right";
}) {
  const cols = twoCol
    ? [papers.filter((_, i) => i % 2 === 0), papers.filter((_, i) => i % 2 === 1)]
    : [papers];
  return (
    <Box
      key={page}
      sx={{
        mt: 3,
        display: "grid",
        gridTemplateColumns: twoCol ? "1fr 1fr" : "1fr",
        gap: 2,
        alignItems: "start",
        animation: `${slideDir === "left" ? "archiveSwipeInRight" : "archiveSwipeInLeft"} .28s ease`,
        "@keyframes archiveSwipeInRight": {
          from: { opacity: 0, transform: "translateX(32px)" },
          to: { opacity: 1, transform: "translateX(0)" },
        },
        "@keyframes archiveSwipeInLeft": {
          from: { opacity: 0, transform: "translateX(-32px)" },
          to: { opacity: 1, transform: "translateX(0)" },
        },
      }}
    >
      {cols.map((col, ci) => (
        <Box key={ci} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {col.map((p) => (
            <ArchiveCard key={p.key} p={p} />
          ))}
        </Box>
      ))}
    </Box>
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
// language the report uses for step status), so a card's color reads as "how well did it do".
function scoreBand(theme: Theme, q: number): { fg: string; soft: string } {
  const t = theme.tokens;
  if (q >= 0.6) return { fg: t.green, soft: t.greenSoft };
  if (q >= 0.4) return { fg: t.amber, soft: t.amberSoft };
  return { fg: t.red, soft: t.redSoft };
}

// The score in the card header: a two-line "Bayesify / Score" label, right-aligned against the big
// band-colored number to its right (which spans both label lines). Falls back to a neutral "—" for
// papers without a quality score (e.g. Human ratings that were never graded).
function ScoreBadge({ p }: { p: ArchivePaper }) {
  const theme = useTheme();
  const q = p.quality_score;
  const band = q != null ? scoreBand(theme, q) : null;

  // The block still stretches to the header row's height (the height the vertical divider spans); we
  // measure that height and set the width equal to it, so it's a perfect square. Number + label sizes
  // are then derived from that side (proportions chosen so a three-digit "100" fits within the square).
  // A CSS-only aspect-ratio can't do this: on a stretched flex item it collapses the width to zero.
  const ref = useRef<HTMLDivElement>(null);
  const [side, setSide] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // width is content-driven until we know the height, so read height only and never feed width back
    const measure = () => setSide((prev) => (Math.abs(prev - el.offsetHeight) > 0.5 ? el.offsetHeight : prev));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const numSize = side ? side * 0.44 : undefined;
  const labelSize = side ? Math.min(11.5, Math.max(8, side * 0.16)) : undefined;
  const labelSx = {
    ...LABEL_FONT,
    ...(labelSize != null && { fontSize: `${labelSize}px` }),
    display: "block",
    lineHeight: 1.2,
    color: "text.secondary",
  } as const;

  return (
    <Box
      ref={ref}
      sx={{
        flexShrink: 0,
        alignSelf: "stretch",
        width: side || "auto",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        justifyContent: "space-between",
        textAlign: "right",
      }}
    >
      <Typography
        sx={{
          fontSize: numSize != null ? `${numSize}px` : "2.5rem",
          fontWeight: 700,
          lineHeight: 1,
          fontVariantNumeric: "tabular-nums",
          color: band ? band.fg : "text.disabled",
        }}
      >
        {q == null ? "—" : Math.round(q * 100)}
      </Typography>
      <Box>
        <Typography sx={labelSx}>Bayesify</Typography>
        <Typography sx={labelSx}>Score</Typography>
      </Box>
    </Box>
  );
}

// The card title: the paper title as the card's stretched link, clamped to two lines so every card
// header is the same height. When the title is longer, a circled chevron on the right — vertically
// centered against the two title lines — expands it in place (and rotates to point up). Overflow is
// measured (ResizeObserver) against the clamped box at the current column width, so the control only
// appears when the title genuinely spills past two lines.
function ArchiveTitle({ p }: { p: ArchivePaper }) {
  const title = p.paper_title ?? p.source_label;
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const ref = useRef<HTMLElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      // only meaningful while clamped; when expanded the box grows to fit and we keep the last verdict
      if (expanded) return;
      setOverflowing(el.scrollHeight > el.clientHeight + 1);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [title, expanded]);

  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
      <Typography
        ref={ref}
        variant="h6"
        sx={{
          flex: 1,
          minWidth: 0,
          fontWeight: 700,
          lineHeight: 1.25,
          // always reserve exactly two lines so short titles don't make shorter cards. In em (2 lines ×
          // the 1.25 line-height) so it tracks the real rendered line height rather than assuming a
          // pixel size — a hardcoded rem drifts from the true two-line height and reintroduces the gap.
          minHeight: "2.5em",
          ...(!expanded && {
            display: "-webkit-box",
            WebkitBoxOrient: "vertical",
            WebkitLineClamp: 2,
            overflow: "hidden",
          }),
        }}
      >
        {/* stretched link: the ::after overlay covers the whole card, so a click anywhere opens the
            report. Genuinely-interactive children (the expand control, Read paper, the tag toggles) sit
            above it via z-index and keep their own behavior. */}
        <Link
          component={RouterLink}
          to={`/paper/${p.paper_id}`}
          color="inherit"
          underline="none"
          sx={{ "&::after": { content: '""', position: "absolute", inset: 0, zIndex: 0 } }}
        >
          <MathText>{title}</MathText>
        </Link>
      </Typography>
      {overflowing && (
        // fixed to the two-line block height, so the button stays centered against the first two lines
        // whether the title is collapsed or expanded
        <Box sx={{ flexShrink: 0, height: TITLE_BLOCK_HEIGHT, display: "flex", alignItems: "center" }}>
          <IconButton
            size="small"
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Collapse title" : "Expand title"}
            aria-expanded={expanded}
            // position/zIndex keep the control clickable above the card's stretched-link overlay
            sx={{
              position: "relative",
              zIndex: 1,
              border: 1,
              borderColor: "divider",
              color: "text.secondary",
              "&:hover": { borderColor: "primary.main", color: "primary.main" },
            }}
          >
            <KeyboardArrowDownIcon
              fontSize="small"
              sx={{ transition: "transform .2s ease", transform: expanded ? "rotate(180deg)" : "none" }}
            />
          </IconButton>
        </Box>
      )}
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
          <ArchiveTitle p={p} />
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

// A flex-wrap chip cluster clamped to `rows` lines. When the chips wrap past that height, the overflow
// collapses behind a circular arrow that sits inline immediately after the last visible chip — solid,
// in the category's color, with a white chevron (rotating up when expanded). To keep the arrow
// attached to the last visible chip we render a hidden full-width mirror of every chip, measure how
// many fit in `rows` lines (leaving room for the arrow on the last one), and show only those, then the
// arrow. Re-measured on width changes via ResizeObserver so it adapts to the column width.
function ClampChips({
  children,
  color,
  rows = CHIP_CLAMP_ROWS,
}: {
  children: React.ReactNode;
  color: (typeof GROUPS)[number]["color"];
  rows?: number;
}) {
  const chips = Children.toArray(children);
  const [expanded, setExpanded] = useState(false);
  const [visibleCount, setVisibleCount] = useState(chips.length);
  const mirrorRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = mirrorRef.current;
    if (!el) return;
    const compute = () => {
      const els = Array.from(el.children) as HTMLElement[];
      if (els.length === 0) return;
      const style = getComputedStyle(el);
      const rowGap = parseFloat(style.rowGap) || 0;
      const colGap = parseFloat(style.columnGap) || 0;
      const top0 = els[0].offsetTop;
      const rowH = els[0].offsetHeight;
      const rowOf = (e: HTMLElement) => Math.round((e.offsetTop - top0) / (rowH + rowGap));
      // everything fits within the row budget → no arrow, show all
      if (rowOf(els[els.length - 1]) <= rows - 1) {
        setVisibleCount(els.length);
        return;
      }
      // otherwise take the leading chips that land within `rows` lines…
      let count = 0;
      for (const e of els) {
        if (rowOf(e) > rows - 1) break;
        count++;
      }
      // …then, if the last of those sits on the final line, drop chips until the arrow fits beside it
      const width = el.clientWidth;
      while (count > 0 && rowOf(els[count - 1]) === rows - 1) {
        const last = els[count - 1];
        if (last.offsetLeft + last.offsetWidth + colGap + CHIP_TOGGLE_SIZE <= width) break;
        count--;
      }
      setVisibleCount(count);
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
  }, [chips.length, rows]);

  const overflowing = visibleCount < chips.length;
  const shown = expanded ? chips : chips.slice(0, visibleCount);
  const clusterSx = { display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.75 } as const;

  return (
    <Box sx={{ position: "relative" }}>
      {/* hidden mirror of every chip at full width — measured to decide how many fit (see above) */}
      <Box
        ref={mirrorRef}
        aria-hidden
        sx={{ ...clusterSx, position: "absolute", top: 0, left: 0, right: 0, visibility: "hidden", pointerEvents: "none" }}
      >
        {chips}
      </Box>
      <Box sx={clusterSx}>
        {shown}
        {overflowing && (
          <IconButton
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Show fewer tags" : "Show more tags"}
            aria-expanded={expanded}
            sx={{
              width: CHIP_TOGGLE_SIZE,
              height: CHIP_TOGGLE_SIZE,
              flexShrink: 0,
              bgcolor: `${color}.main`,
              color: `${color}.contrastText`,
              // position/zIndex keep the toggle clickable above the card's stretched-link overlay
              position: "relative",
              zIndex: 1,
              "&:hover": { bgcolor: `${color}.main`, filter: "brightness(0.92)" },
            }}
          >
            <KeyboardArrowDownIcon
              fontSize="small"
              sx={{ transition: "transform .2s ease", transform: expanded ? "rotate(180deg)" : "none" }}
            />
          </IconButton>
        )}
      </Box>
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
        <ClampChips color={g.color}>
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

