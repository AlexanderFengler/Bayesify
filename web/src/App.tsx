import { Box, Button, CircularProgress, Container, Typography } from "@mui/material";
import { lazy, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { getPaper } from "./api";
import type { GateFailure } from "./Analyzing";
import { useApp } from "./AppContext";
import { ErrorBoundary } from "./ErrorBoundary";
import { Landing } from "./Landing";
import { Layout } from "./Layout";
import { formatByline } from "./paper";
import { type PaperState, STAGES } from "./types";

// Route-level code splitting: every page below the landing entry loads on demand, so a first-time
// visitor no longer downloads the report / rate / archive / etc. code up front — each chunk is
// fetched (and cached) only when its route is first hit. Landing stays eagerly imported: it is the
// entry page, so splitting it would only add a load waterfall + spinner to the most common first
// paint (and it already needs KaTeX/MathText via its rubrics section). The Suspense fallback that
// covers each pending chunk lives in Layout, so only the content area shows it — chrome stays put.
const Analyzing = lazy(() => import("./Analyzing").then((m) => ({ default: m.Analyzing })));
const Archive = lazy(() => import("./Archive").then((m) => ({ default: m.Archive })));
const Calibration = lazy(() => import("./Calibration").then((m) => ({ default: m.Calibration })));
const Inventory = lazy(() => import("./Inventory").then((m) => ({ default: m.Inventory })));
const LocalNotice = lazy(() => import("./Inventory").then((m) => ({ default: m.LocalNotice })));
const Rate = lazy(() => import("./Rate").then((m) => ({ default: m.Rate })));
const Report = lazy(() => import("./Report").then((m) => ({ default: m.Report })));
const AboutUs = lazy(() => import("./AboutUs").then((m) => ({ default: m.AboutUs })));

// The whole app is client-side routed: a single Layout holds the app-wide state (mode, the upload
// draft, the streaming lifecycle, the privacy modal) and every URL renders a page into its <Outlet />.
// The thin *Route wrappers below bridge router params + AppContext to each page's prop interface, so
// the page components themselves stay router-agnostic.
export function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<LandingRoute />} />
            {/* the old standalone pages fold into the main page now — keep the URLs alive as redirects
                (bookmarks, shared links): /start → the main page, /guide + /rubrics → their sections */}
            <Route path="/start" element={<Navigate to="/" replace />} />
            <Route path="/guide" element={<Navigate to="/#how-it-works" replace />} />
            <Route path="/rubrics" element={<Navigate to="/#rubrics" replace />} />
            <Route path="/processing" element={<ProcessingRoute />} />
            {/* splat captures the optional /full segment; one route element so the component persists
                across the summary↔full morph */}
            <Route path="/paper/:id/*" element={<PaperRoute />} />
            <Route path="/rate/:id" element={<RateRoute />} />
            <Route path="/calibration" element={<CalibrationRoute />} />
            <Route path="/archive" element={<ArchiveRoute />} />
            <Route path="/about" element={<AboutUsRoute />} />
            {/* the page used to live at /supported — keep the URL alive as a redirect */}
            <Route path="/supported" element={<Navigate to="/about" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}

function LandingRoute() {
  const app = useApp();
  return (
    <Landing
      mode={app.mode}
      setMode={app.setMode}
      profile={app.profile}
      setProfile={app.setProfile}
      rubrics={app.rubrics}
      identifier={app.identifier}
      setIdentifier={app.setIdentifier}
      file={app.file}
      setFile={app.setFile}
      dragging={app.dragging}
      setDragging={app.setDragging}
      fileInput={app.fileInput}
      onStart={app.start}
      fetchError={app.fetchError}
    />
  );
}

function ArchiveRoute() {
  return <Archive />;
}

function ProcessingRoute() {
  const { running, archiveHit, error, stageState, file, identifier, mode, reset, paper, rerunPaper } = useApp();
  const navigate = useNavigate();
  if (error) return <ErrorPage error={error} onRetry={reset} />;
  if (archiveHit) return <ArchiveRedirect />;
  // A direct hit / refresh on /processing has no run in flight. We show an idle panel rather than
  // redirecting — a render-time <Navigate> here would fire during the completion transition (when
  // running briefly reads false on the old location) and bounce an in-flight run back to /start.
  if (!running) {
    return (
      <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 }, textAlign: "center" }}>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          No analysis is in progress.
        </Typography>
        <Button variant="contained" disableElevation onClick={() => navigate("/")}>
          Start an analysis
        </Button>
      </Container>
    );
  }
  // an identifier job fetches instead of ingesting an upload → swap the first step
  const modeStages = mode === "local" ? STAGES.slice(0, 3) : STAGES;
  const stages = !file && identifier.trim() ? ["fetch", ...modeStages.slice(1)] : modeStages;
  // Once parse completes mid-run, prefer the extracted title (+ an authors · year byline) over the
  // filename; until then fall back to the filename / pasted identifier.
  const source = paper?.paper_title ?? file?.name ?? identifier;
  const byline = paper ? formatByline(paper.paper_authors, paper.paper_year) : null;
  // The gate stop: when the run finished but the paper was judged out of scope (not Bayesian, or the
  // rubric doesn't apply to its type), the flow stays here — the deciding step is shown as a red
  // cross and the reasons render below (Layout marked that stage "failed" and did not navigate away).
  const r = paper?.result;
  const gate: GateFailure | null =
    r && !r.relevance.overridden && (r.relevance.label === "no" || r.not_applicable_reason)
      ? {
          isReview: r.not_applicable_reason === "not_an_application",
          rationale:
            (r.not_applicable_reason === "not_an_application" && r.paper_class?.rationale) || r.relevance.rationale,
          confidence:
            r.not_applicable_reason === "not_an_application" && r.paper_class
              ? r.paper_class.confidence
              : r.relevance.confidence,
          onRerun: () => rerunPaper(paper!.paper_id),
          onReset: reset,
        }
      : null;
  return (
    <Analyzing
      stageState={stageState}
      stages={stages}
      source={source}
      byline={byline}
      paperClass={paper?.paper_class}
      gate={gate}
    />
  );
}

function ArchiveRedirect() {
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", px: 3 }}
    >
      <Box sx={{ textAlign: "center" }}>
        <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.02em" }}>
          Found in the archive.
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          This paper has already been analyzed. Taking you to its report…
        </Typography>
        <CircularProgress size={22} sx={{ mt: 3 }} aria-label="Opening archived report" />
      </Box>
    </Box>
  );
}

// Dispatches a paper by payload (report / inventory / local notice / failed). Uses the in-memory
// paper when it matches the URL; otherwise refetches by id so refresh, bookmark, and share all work.
function PaperRoute() {
  const params = useParams();
  const id = params.id;
  const expanded = (params["*"] ?? "") === "full"; // /paper/:id/full → the full report
  const app = useApp();
  const navigate = useNavigate();
  const [fetched, setFetched] = useState<PaperState | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const fromState = app.paper && app.paper.paper_id === id ? app.paper : null;
  const paper = fromState ?? fetched;

  useEffect(() => {
    if (fromState || !id) return;
    setFetched(null);
    setErr(null);
    getPaper(id)
      .then(setFetched)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [id, fromState]);

  if (err) return <ErrorPage error={err} onRetry={app.reset} />;
  if (!paper) return <LoadingPage label="Loading paper…" />;
  if (paper.status === "failed") {
    return <ErrorPage error={paper.error ?? "assessment failed"} onRetry={app.reset} />;
  }
  if (paper.result) {
    return <Report paper={paper} onReset={app.reset} onRerun={app.rerunPaper} expanded={expanded} />;
  }
  if (paper.inventory) {
    return <Inventory paper={paper} onReset={app.reset} onRate={(pid) => navigate(`/rate/${pid}`)} />;
  }
  if (paper.local_notice) {
    return <LocalNotice notice={paper.local_notice} source={paper.source_label} onReset={app.reset} />;
  }
  return <LoadingPage label="Preparing…" />;
}

function RateRoute() {
  const { id } = useParams();
  const { ratingPending } = useApp();
  const navigate = useNavigate();
  if (!id) return <Navigate to="/" replace />;
  // Canceling or finishing a blind rating returns to the main page (a fresh analysis), not back
  // into the rating's origin. `pending` holds the page in its loading state while the background
  // detector run (which feeds the rating context) finishes — so the rate flow skips /processing.
  return <Rate paperId={id} pending={ratingPending === id} onExit={() => navigate("/")} />;
}

function CalibrationRoute() {
  const { exitToMain } = useApp();
  return <Calibration onExit={exitToMain} />;
}

function AboutUsRoute() {
  return <AboutUs />;
}

// --- shared status pages (loading / error). The permanent header is supplied by Layout; these just
// fill the routed content area. ---------------------------------------------------------------------

function LoadingPage({ label }: { label: string }) {
  return (
    <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary" }}>
        <CircularProgress size={20} />
        <Typography>{label}</Typography>
      </Box>
    </Box>
  );
}

// A solid magenta card (not glass) so the error reads clearly over either aurora; white text keeps it
// legible on the #ec008c fill, and the retry action sits full-width at the bottom rather than inline.
function ErrorPage({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 } }}>
      <Box
        sx={{
          bgcolor: "#ec008c",
          color: "#fff",
          borderRadius: 2,
          p: { xs: 2.5, md: 3 },
          boxShadow: "0 10px 30px rgba(236,0,140,0.35)",
        }}
      >
        <Typography variant="h6" component="h2" sx={{ fontWeight: 700, mb: 1 }}>
          Something went wrong
        </Typography>
        <Typography sx={{ color: "rgba(255,255,255,0.96)", lineHeight: 1.5 }}>{error}</Typography>
        <Button
          fullWidth
          onClick={onRetry}
          sx={{
            mt: 3,
            bgcolor: "#fff",
            color: "#ec008c",
            fontWeight: 700,
            "&:hover": { bgcolor: "rgba(255,255,255,0.88)" },
          }}
        >
          Try again
        </Button>
      </Box>
    </Container>
  );
}
