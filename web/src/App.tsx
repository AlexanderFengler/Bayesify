import { Alert, AlertTitle, Box, Button, CircularProgress, Container, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { getPaper } from "./api";
import { Analyzing } from "./Analyzing";
import { useApp } from "./AppContext";
import { Calibration } from "./Calibration";
import { Cover } from "./Cover";
import { Guide } from "./Guide";
import { Inventory, LocalNotice } from "./Inventory";
import { Landing } from "./Landing";
import { Layout } from "./Layout";
import { formatByline } from "./paper";
import { Rate } from "./Rate";
import { Report } from "./Report";
import { Rubrics } from "./Rubrics";
import { SupportedBy } from "./SupportedBy";
import { LOCAL_STAGES, type PaperState, STAGES } from "./types";

// The whole app is client-side routed: a single Layout holds the app-wide state (mode, the upload
// draft, the streaming lifecycle, the privacy modal) and every URL renders a page into its <Outlet />.
// The thin *Route wrappers below bridge router params + AppContext to each page's prop interface, so
// the page components themselves stay router-agnostic.
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<CoverRoute />} />
          <Route path="/start" element={<LandingRoute />} />
          <Route path="/processing" element={<ProcessingRoute />} />
          {/* splat captures the optional /full segment; one route element so the component persists
              across the summary↔full morph */}
          <Route path="/paper/:id/*" element={<PaperRoute />} />
          <Route path="/rate/:id" element={<RateRoute />} />
          <Route path="/calibration" element={<CalibrationRoute />} />
          <Route path="/rubrics" element={<RubricsRoute />} />
          <Route path="/guide" element={<GuideRoute />} />
          <Route path="/supported" element={<SupportedByRoute />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

function CoverRoute() {
  const navigate = useNavigate();
  return <Cover onGetStarted={() => navigate("/start")} />;
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
    />
  );
}

function RubricsRoute() {
  const { exitToMain } = useApp();
  return <Rubrics onExit={exitToMain} />;
}

function ProcessingRoute() {
  const { running, error, stageState, file, identifier, mode, reset, paper } = useApp();
  const navigate = useNavigate();
  if (error) return <ErrorPage error={error} onRetry={reset} />;
  // A direct hit / refresh on /processing has no run in flight. We show an idle panel rather than
  // redirecting — a render-time <Navigate> here would fire during the completion transition (when
  // running briefly reads false on the old location) and bounce an in-flight run back to /start.
  if (!running) {
    return (
      <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 }, textAlign: "center" }}>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          No analysis is in progress.
        </Typography>
        <Button variant="contained" disableElevation onClick={() => navigate("/start")}>
          Start an analysis
        </Button>
      </Container>
    );
  }
  // an identifier job fetches instead of ingesting an upload → swap the first step
  const stages =
    !file && identifier.trim()
      ? ["fetch", ...(mode === "local" ? LOCAL_STAGES : STAGES).slice(1)]
      : mode === "local"
        ? LOCAL_STAGES
        : STAGES;
  // Once parse completes mid-run, prefer the extracted title (+ an authors · year byline) over the
  // filename; until then fall back to the filename / pasted identifier.
  const source = paper?.paper_title ?? file?.name ?? identifier;
  const byline = paper ? formatByline(paper.paper_authors, paper.paper_year) : null;
  return <Analyzing stageState={stageState} stages={stages} source={source} byline={byline} />;
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
  if (!id) return <Navigate to="/start" replace />;
  // Cancelling or finishing a blind rating returns to the start page (a fresh analysis), not back
  // into the rating's origin. `pending` holds the page in its loading state while the background
  // detector run (which feeds the rating context) finishes — so the rate flow skips /processing.
  return <Rate paperId={id} pending={ratingPending === id} onExit={() => navigate("/start")} />;
}

function CalibrationRoute() {
  const { exitToMain } = useApp();
  return <Calibration onExit={exitToMain} />;
}

function GuideRoute() {
  const { exitToMain } = useApp();
  return <Guide onExit={exitToMain} />;
}

function SupportedByRoute() {
  const { exitToMain } = useApp();
  return <SupportedBy onExit={exitToMain} />;
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

function ErrorPage({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 } }}>
      <Alert
        severity="error"
        action={
          <Button color="inherit" size="small" onClick={onRetry}>
            Try again
          </Button>
        }
      >
        <AlertTitle>Something went wrong</AlertTitle>
        {error}
      </Alert>
    </Container>
  );
}
