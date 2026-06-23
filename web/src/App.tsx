import { Alert, AlertTitle, Box, Button, CircularProgress, Container, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { getPaper } from "./api";
import { Analyzing } from "./Analyzing";
import { useApp } from "./AppContext";
import { Calibration } from "./Calibration";
import { Cover } from "./Cover";
import { Guide } from "./Guide";
import { TopBar } from "./HeroShell";
import { Inventory, LocalNotice } from "./Inventory";
import { Landing } from "./Landing";
import { Layout } from "./Layout";
import { Rate } from "./Rate";
import { Report } from "./Report";
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
          <Route path="/paper/:id" element={<PaperRoute />} />
          <Route path="/rate/:id" element={<RateRoute />} />
          <Route path="/calibration" element={<CalibrationRoute />} />
          <Route path="/guide" element={<GuideRoute />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

function CoverRoute() {
  const { mode } = useApp();
  const navigate = useNavigate();
  return <Cover mode={mode} onGetStarted={() => navigate("/start")} />;
}

function LandingRoute() {
  const app = useApp();
  const navigate = useNavigate();
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
      onGuide={() => navigate("/guide")}
      onPrivacy={app.openPrivacy}
      onCalibration={() => navigate("/calibration")}
    />
  );
}

function ProcessingRoute() {
  const { running, error, stageState, file, identifier, mode, reset } = useApp();
  const navigate = useNavigate();
  if (error) return <ErrorPage mode={mode} error={error} onRetry={reset} />;
  // A direct hit / refresh on /processing has no run in flight. We show an idle panel rather than
  // redirecting — a render-time <Navigate> here would fire during the completion transition (when
  // running briefly reads false on the old location) and bounce an in-flight run back to /start.
  if (!running) {
    return (
      <PageShell mode={mode}>
        <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 }, textAlign: "center" }}>
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            No analysis is in progress.
          </Typography>
          <Button variant="contained" disableElevation onClick={() => navigate("/start")}>
            Start an analysis
          </Button>
        </Container>
      </PageShell>
    );
  }
  // an identifier job fetches instead of ingesting an upload → swap the first step
  const stages =
    !file && identifier.trim()
      ? ["fetch", ...(mode === "local" ? LOCAL_STAGES : STAGES).slice(1)]
      : mode === "local"
        ? LOCAL_STAGES
        : STAGES;
  return <Analyzing stageState={stageState} stages={stages} source={file?.name ?? identifier} mode={mode} />;
}

// Dispatches a paper by payload (report / inventory / local notice / failed). Uses the in-memory
// paper when it matches the URL; otherwise refetches by id so refresh, bookmark, and share all work.
function PaperRoute() {
  const { id } = useParams();
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

  if (err) return <ErrorPage mode={app.mode} error={err} onRetry={app.reset} />;
  if (!paper) return <LoadingPage mode={app.mode} label="Loading paper…" />;
  if (paper.status === "failed") {
    return <ErrorPage mode={app.mode} error={paper.error ?? "assessment failed"} onRetry={app.reset} />;
  }
  if (paper.result) {
    return <Report paper={paper} mode={app.mode} onReset={app.reset} onRerun={app.rerunPaper} />;
  }
  if (paper.inventory) {
    return <Inventory paper={paper} onReset={app.reset} onRate={(pid) => navigate(`/rate/${pid}`)} />;
  }
  if (paper.local_notice) {
    return <LocalNotice notice={paper.local_notice} source={paper.source_label} onReset={app.reset} />;
  }
  return <LoadingPage mode={app.mode} label="Preparing…" />;
}

function RateRoute() {
  const { id } = useParams();
  const { mode } = useApp();
  const navigate = useNavigate();
  if (!id) return <Navigate to="/start" replace />;
  return <Rate paperId={id} mode={mode} onExit={() => navigate(-1)} />;
}

function CalibrationRoute() {
  const { mode } = useApp();
  const navigate = useNavigate();
  return <Calibration mode={mode} onExit={() => navigate(-1)} />;
}

function GuideRoute() {
  const { mode } = useApp();
  const navigate = useNavigate();
  return <Guide mode={mode} onExit={() => navigate(-1)} />;
}

// --- shared full-bleed status pages (loading / error), top-barred like the result pages ----------

function PageShell({ mode, children }: { mode: "full" | "local"; children: React.ReactNode }) {
  return (
    <Box sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column", bgcolor: "background.default" }}>
      <TopBar mode={mode} />
      <Box sx={{ flex: 1 }}>{children}</Box>
    </Box>
  );
}

function LoadingPage({ mode, label }: { mode: "full" | "local"; label: string }) {
  return (
    <PageShell mode={mode}>
      <Box sx={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary" }}>
          <CircularProgress size={20} />
          <Typography>{label}</Typography>
        </Box>
      </Box>
    </PageShell>
  );
}

function ErrorPage({ mode, error, onRetry }: { mode: "full" | "local"; error: string; onRetry: () => void }) {
  return (
    <PageShell mode={mode}>
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
    </PageShell>
  );
}
