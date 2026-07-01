import { Box, Fade } from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useOutlet } from "react-router-dom";
import { SwitchTransition } from "react-transition-group";
import { fetchRubrics, getPaper, rerun, type RubricSummary, streamProgress, submitPaper } from "./api";
import { AppContext, type AppState } from "./AppContext";
import { Aurora } from "./Aurora";
import { Footer } from "./Footer";
import { Header } from "./Header";
import type { PaperState } from "./types";

// The root layout: it owns the app-wide state (mode, the upload draft, the streaming lifecycle) and
// exposes it through AppContext. It sits inside the Router, so its actions can navigate. Every route
// renders into <Outlet />.
export function Layout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // Remember the last "meaningful" page (cover / start / a report) so the reference pages' Back
  // buttons can return there, skipping transient stops like /processing. Defaults to the cover.
  const lastMainRef = useRef("/");
  useEffect(() => {
    if (pathname === "/" || pathname === "/start" || pathname.startsWith("/paper/")) {
      lastMainRef.current = pathname;
    }
  }, [pathname]);
  const exitToMain = useCallback(() => navigate(lastMainRef.current), [navigate]);
  const [mode, setMode] = useState<"full" | "local">("full");
  const [profile, setProfile] = useState("synthesis");
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [identifier, setIdentifier] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stageState, setStageState] = useState<Record<string, "running" | "done">>({});
  const [running, setRunning] = useState(false);
  const [paper, setPaper] = useState<PaperState | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The paper id whose blind-rating pipeline is still running. The rate flow jumps straight to the
  // rating page (no /processing flash) and waits there until this clears — the rating context needs
  // the detector inventory, which isn't ready until the run finishes.
  const [ratingPending, setRatingPending] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // The available rubrics for the analysis picker (synthesis default; Gelman, etc.).
  useEffect(() => {
    fetchRubrics()
      .then(setRubrics)
      .catch(() => {});
  }, []);

  const reset = useCallback(() => {
    setIdentifier("");
    setFile(null);
    setStageState({});
    setPaper(null);
    setError(null);
    setRunning(false);
    setRatingPending(null);
    navigate("/start");
  }, [navigate]);

  // Stream one paper_id to completion and route to its result. Shared by a fresh run and a rerun.
  // `rateOnDone` opens the blind rating form once the paper is ingested (the rate-from-landing flow).
  const track = useCallback(
    (paperId: string, opts?: { rateOnDone?: boolean }) => {
      setStageState({});
      setError(null);
      setPaper(null); // clear any prior run so the Analyzing screen starts clean
      setRunning(true);
      let metaFetched = false;
      streamProgress(
        paperId,
        (e) => {
          if (e.type === "stage" && e.stage) {
            setStageState((prev) => ({ ...prev, [e.stage!]: e.state ?? "running" }));
            // Once parsing is done the backend knows the paper's title/authors/year — pull them in
            // (once) so the Analyzing screen shows the real paper, not the filename.
            if (e.stage === "parse" && e.state === "done" && !metaFetched) {
              metaFetched = true;
              getPaper(paperId).then(setPaper).catch(() => {});
            }
          }
        },
        async () => {
          const result = await getPaper(paperId);
          setPaper(result);
          setRatingPending(null); // the inventory is ready now — the rating page can load its context
          if (result.status === "failed") {
            setError(result.error ?? "assessment failed");
          }
          // The paper page dispatches by payload (report / inventory / local notice / failed); the
          // rate flow already navigated to the blind form (below) — re-navigating to the same URL is a
          // harmless no-op. We deliberately do NOT clear `running` here: react-router navigation is a
          // concurrent transition, so an urgent setRunning(false) would render /processing for one
          // frame with running=false and trip its idle state mid-flight. `running` is cleared only by
          // reset()/the next run. `replace`: /processing is a transient stop, so swap it out of
          // history — browser-Back from the report lands on /start, not the processing screen.
          navigate(opts?.rateOnDone ? `/rate/${paperId}` : `/paper/${paperId}`, { replace: true });
        },
      );
    },
    [navigate],
  );

  // `intent="rate"` runs the on-device front half (detect only, no LLM) and then opens the blind
  // rating form — so a rater can self-rate straight from the landing page, not only after Analyze.
  const start = useCallback(
    async (intent: "analyze" | "rate" = "analyze") => {
      if (!file && !identifier.trim()) return;
      const runMode = intent === "rate" ? "local" : mode;
      setStageState({});
      setError(null);
      setRunning(true);
      // Analyze shows the /processing screen; rate skips it — once we have an id we jump straight to
      // the blind-rating page, which shows its own "loading the rating context" state while the
      // (background) detector run finishes. ratingPending keeps that page in its loading state.
      if (intent === "analyze") navigate("/processing");
      try {
        const paperId = await submitPaper({ file, identifier, mode: runMode, profile });
        if (intent === "rate") {
          setRatingPending(paperId);
          navigate(`/rate/${paperId}`, { replace: true });
        }
        track(paperId, { rateOnDone: intent === "rate" });
      } catch (err) {
        // Surface the error on /processing (its error branch wins before the !running redirect). Keep
        // `running` set so there's no race; reset() clears it. Route there even on the rate path,
        // where a submit failure means we never reached the rating page.
        setError(err instanceof Error ? err.message : String(err));
        navigate("/processing");
      }
    },
    [file, identifier, mode, profile, track, navigate],
  );

  // Gate-page escape hatch: re-run a short-circuited paper as 'partial' so it gets fully graded.
  const rerunPaper = useCallback(
    async (paperId: string) => {
      setError(null);
      setRunning(true); // mark a run active BEFORE navigating, or /processing redirects to /start
      navigate("/processing");
      try {
        await rerun(paperId);
        track(paperId);
      } catch (err) {
        // Keep `running` set (see start's catch) so the error shows on /processing without a race.
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [track, navigate],
  );

  const value = useMemo<AppState>(
    () => ({
      mode,
      setMode,
      profile,
      setProfile,
      rubrics,
      identifier,
      setIdentifier,
      file,
      setFile,
      dragging,
      setDragging,
      fileInput,
      running,
      ratingPending,
      stageState,
      paper,
      setPaper,
      error,
      start,
      rerunPaper,
      reset,
      exitToMain,
    }),
    [
      mode,
      profile,
      rubrics,
      identifier,
      file,
      dragging,
      running,
      ratingPending,
      stageState,
      paper,
      error,
      start,
      rerunPaper,
      reset,
      exitToMain,
    ],
  );

  return (
    <AppContext.Provider value={value}>
      {/* the living gradient, fixed behind everything — drifts twice as fast while processing */}
      <Aurora fast={pathname === "/processing"} />
      {/* the app frame: header + footer are transparent and pinned outside the scroll area, so the
          aurora shows through them at all times and content never slides underneath. Only the middle
          scrolls. */}
      <Box
        sx={{
          position: "relative",
          zIndex: 1,
          height: "100dvh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <Header />
        <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column" }}>
          <FadingOutlet />
        </Box>
        <Footer />
      </Box>
    </AppContext.Provider>
  );
}

// Cross-fades the routed content (and only the content — header/footer are pinned outside this).
// Keyed on the path, SwitchTransition's "out-in" mode fades the old page out, then the new page in.
// Every route is transparent: content floats directly on the aurora (panels are frosted glass), so
// the fade always resolves to the living background — never to a flat surface — keeping it
// uninterrupted through the transition.
function FadingOutlet() {
  const { pathname } = useLocation();
  const outlet = useOutlet();
  // Group /paper/:id and /paper/:id/full under one key so navigating between the summary and the full
  // report does NOT trigger a page cross-fade — that morph is animated inside the (persistent) Report.
  const key = pathname.startsWith("/paper/")
    ? "/" + pathname.split("/").slice(1, 3).join("/")
    : pathname;
  return (
    <SwitchTransition mode="out-in">
      <Fade key={key} timeout={200} appear>
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column" }}>{outlet}</Box>
      </Fade>
    </SwitchTransition>
  );
}
