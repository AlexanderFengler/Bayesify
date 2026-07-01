import SearchIcon from "@mui/icons-material/Search";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  InputAdornment,
  Link,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPapers } from "./api";
import { MathText } from "./MathText";
import { articleUrl, formatByline } from "./paper";
import type { ArchiveFacets, ArchivePaper } from "./types";

const EMPTY_FACETS: ArchiveFacets = { paper_type: [], discipline: [], methods: [] };
// the facet groups, in render order — key into the facets payload + the paper's own auto-tag arrays
const GROUPS = [
  { key: "paper_type", label: "Paper type", field: "paper_type" },
  { key: "discipline", label: "Discipline", field: "discipline" },
  { key: "methods", label: "Methods & software", field: "methods" },
] as const;

const pretty = (s: string) => s.replace(/[-_]/g, " ");

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
  });
  const [papers, setPapers] = useState<ArchivePaper[]>([]);
  const [facets, setFacets] = useState<ArchiveFacets>(EMPTY_FACETS);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  const clearAll = () => setSelected({ paper_type: [], discipline: [], methods: [] });

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            Archive
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 1440 }}>
            Every paper run through Bayesify, tagged automatically by paper type, discipline, and the
            methods & software detected. Search the text or filter by tags.
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

      {/* facet filter chips — one row per group; clicking a chip AND-filters the list */}
      <Box sx={{ mt: 2.5, display: "flex", flexDirection: "column", gap: 1.25 }}>
        {GROUPS.map((g) => {
          const values = facets[g.key as keyof ArchiveFacets];
          if (values.length === 0) return null;
          return (
            <Box key={g.key} sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap" }}>
              <Typography
                sx={{ fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "text.secondary", minWidth: 128 }}
              >
                {g.label}
              </Typography>
              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                {values.map((v) => {
                  const on = selected[g.key].includes(v);
                  return (
                    <Chip
                      key={v}
                      label={pretty(v)}
                      size="small"
                      color={on ? "primary" : "default"}
                      variant={on ? "filled" : "outlined"}
                      onClick={() => toggle(g.key, v)}
                    />
                  );
                })}
              </Box>
            </Box>
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
        <Box
          sx={{
            mt: 3,
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" },
            gap: 2,
            alignItems: "start",
          }}
        >
          {papers.map((p) => (
            <ArchiveCard key={p.key} p={p} />
          ))}
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

function ArchiveCard({ p }: { p: ArchivePaper }) {
  const navigate = useNavigate();
  const byline = formatByline(p.paper_authors, p.paper_year);
  const url = articleUrl(p.source_label); // link the title when the paper was submitted by URL
  const scoreLine = useMemo(() => {
    const bits: string[] = [];
    if (p.quality_score != null) bits.push(`Score ${Math.round(p.quality_score * 100)}`);
    if (p.coverage_present != null && p.coverage_applicable != null)
      bits.push(`Coverage ${p.coverage_present}/${p.coverage_applicable}`);
    if (p.relevance_label) bits.push(p.relevance_label);
    return bits.join(" · ");
  }, [p]);

  const groupChips = (values: string[], color: "default" | "info" | "success") =>
    values.map((v) => (
      <Chip key={v} label={pretty(v)} size="small" variant="outlined" color={color} sx={{ height: 24 }} />
    ));

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 2 }}>
      {/* title block and the Open-report button on one line, 5:1 on wide screens (stacked on phones) */}
      <Box sx={{ display: "flex", flexDirection: { xs: "column", sm: "row" }, alignItems: { sm: "flex-start" }, gap: 2 }}>
        <Box sx={{ flex: { sm: 5 }, minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.25 }}>
            {url ? (
              <Link href={url} target="_blank" rel="noreferrer" color="inherit" underline="none">
                <MathText>{p.paper_title ?? p.source_label}</MathText>
              </Link>
            ) : (
              <MathText>{p.paper_title ?? p.source_label}</MathText>
            )}
          </Typography>
          {byline && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {byline}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            <Chip
              label={p.mode === "full" ? "AI" : "Human"}
              size="small"
              color={p.mode === "full" ? "primary" : "secondary"}
              variant="outlined"
              sx={{ height: 20, mr: 1 }}
            />
            {scoreLine}
          </Typography>
        </Box>
        <Box sx={{ flex: { sm: 1 }, display: "flex", justifyContent: { xs: "flex-start", sm: "flex-end" } }}>
          <Button size="small" onClick={() => navigate(`/paper/${p.paper_id}`)} sx={{ flexShrink: 0 }}>
            Open report
          </Button>
        </Box>
      </Box>

      {(p.paper_type.length > 0 || p.discipline.length > 0 || p.methods.length > 0) && (
        <Box sx={{ mt: 1.5, display: "flex", gap: 0.75, flexWrap: "wrap" }}>
          {groupChips(p.paper_type, "default")}
          {groupChips(p.discipline, "info")}
          {groupChips(p.methods, "success")}
        </Box>
      )}
    </Paper>
  );
}
