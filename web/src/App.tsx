import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRubrics, getPaper, rerun, type RubricSummary, streamProgress, submitPaper } from "./api";
import { Analyzing } from "./Analyzing";
import { Calibration } from "./Calibration";
import { Guide } from "./Guide";
import { Inventory, LocalNotice } from "./Inventory";
import { Landing } from "./Landing";
import { PrivacyModal } from "./Modal";
import { Rate } from "./Rate";
import { Report } from "./Report";
import { LOCAL_STAGES, STAGES, type PaperState } from "./types";

type Phase = "idle" | "running" | "done" | "error";
type ModalKind = "privacy" | null;
const PRIVACY_ACK_KEY = "bayesify.privacy.ack"; // set once the first-run disclosure is acknowledged

export function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<"full" | "local">("full");
  const [profile, setProfile] = useState("synthesis"); // which rubric to grade against
  const [rubrics, setRubrics] = useState<RubricSummary[]>([]);
  const [identifier, setIdentifier] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stageState, setStageState] = useState<Record<string, "running" | "done">>({});
  const [paper, setPaper] = useState<PaperState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ratingPaperId, setRatingPaperId] = useState<string | null>(null); // blind-rating takeover
  const [showCalibration, setShowCalibration] = useState(false); // calibration view takeover
  const [showGuide, setShowGuide] = useState(false); // user-guide view takeover
  const [modal, setModal] = useState<ModalKind>(null);
  const [firstRun, setFirstRun] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // First visit: show the privacy/mode disclosure before anything is uploaded (PRIVACY.md, F3).
  useEffect(() => {
    if (!localStorage.getItem(PRIVACY_ACK_KEY)) {
      setFirstRun(true);
      setModal("privacy");
    }
  }, []);

  // Direct blind-rating entry: /?rate=<paper_id> opens the blind form for an already-ingested paper
  // (a stable link for assigning a rater a paper; the in-app entry is the local detection view).
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("rate");
    if (id) setRatingPaperId(id);
  }, []);

  // The available rubrics for the analysis picker (synthesis default; Gelman, etc.).
  useEffect(() => {
    fetchRubrics()
      .then(setRubrics)
      .catch(() => {});
  }, []);

  const ackPrivacy = useCallback(() => {
    localStorage.setItem(PRIVACY_ACK_KEY, "1");
    setFirstRun(false);
    setModal(null);
  }, []);

  const reset = () => {
    setPhase("idle");
    setIdentifier("");
    setFile(null);
    setStageState({});
    setPaper(null);
    setError(null);
  };

  // Stream one paper_id to completion and load the final result. Shared by a fresh run and a rerun.
  // `rateOnDone` opens the blind rating form once the paper is ingested (the rate-from-landing flow).
  const track = useCallback((paperId: string, opts?: { rateOnDone?: boolean }) => {
    setPhase("running");
    setStageState({});
    setError(null);
    streamProgress(
      paperId,
      (e) => {
        if (e.type === "stage" && e.stage) {
          setStageState((prev) => ({ ...prev, [e.stage!]: e.state ?? "running" }));
        }
      },
      async () => {
        const result = await getPaper(paperId);
        if (result.status === "failed") {
          setPaper(result);
          setError(result.error ?? "assessment failed");
          setPhase("error");
          return;
        }
        if (opts?.rateOnDone) {
          setRatingPaperId(paperId); // the paper is ingested → open the blind form directly
          setPhase("idle");
          return;
        }
        setPaper(result);
        setPhase("done");
      },
    );
  }, []);

  // `intent="rate"` runs the on-device front half (detect only, no LLM) and then opens the blind
  // rating form — so a rater can self-rate straight from the landing page, not only after Analyze.
  const start = useCallback(
    async (intent: "analyze" | "rate" = "analyze") => {
      if (!file && !identifier.trim()) return;
      const runMode = intent === "rate" ? "local" : mode;
      setPhase("running");
      setStageState({});
      setError(null);
      try {
        const paperId = await submitPaper({ file, identifier, mode: runMode, profile });
        track(paperId, { rateOnDone: intent === "rate" });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setPhase("error");
      }
    },
    [file, identifier, mode, profile, track],
  );

  // Gate-page escape hatch: re-run a short-circuited paper as 'partial' so it gets fully graded.
  const rerunPaper = useCallback(
    async (paperId: string) => {
      try {
        await rerun(paperId);
        track(paperId);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setPhase("error");
      }
    },
    [track],
  );

  // The immersive landing (idle + no takeover view) is fully MUI and renders edge-to-edge — it does
  // not use the legacy .page/.container chrome. Every other state still uses the old chrome for now;
  // they'll migrate page by page.
  const isLanding = !ratingPaperId && !showCalibration && !showGuide && phase === "idle";
  if (isLanding) {
    return (
      <>
        <Landing
          mode={mode}
          setMode={setMode}
          profile={profile}
          setProfile={setProfile}
          rubrics={rubrics}
          identifier={identifier}
          setIdentifier={setIdentifier}
          file={file}
          setFile={setFile}
          dragging={dragging}
          setDragging={setDragging}
          fileInput={fileInput}
          onStart={start}
          onGuide={() => setShowGuide(true)}
          onPrivacy={() => setModal("privacy")}
          onCalibration={() => setShowCalibration(true)}
        />
        {modal === "privacy" && (
          <PrivacyModal firstRun={firstRun} onClose={firstRun ? ackPrivacy : () => setModal(null)} />
        )}
      </>
    );
  }

  // The "Analyzing" page is equally immersive (same hero, no card) — render it full-bleed too.
  const isAnalyzing = !ratingPaperId && !showCalibration && !showGuide && phase === "running";
  if (isAnalyzing) {
    // an identifier job fetches instead of ingesting an upload → swap the first step
    const stages =
      !file && identifier.trim()
        ? ["fetch", ...(mode === "local" ? LOCAL_STAGES : STAGES).slice(1)]
        : mode === "local"
          ? LOCAL_STAGES
          : STAGES;
    return (
      <Analyzing
        stageState={stageState}
        stages={stages}
        source={file?.name ?? identifier}
        mode={mode}
      />
    );
  }

  // The done-state result pages are each their own full-bleed page (own top bar) — render directly.
  if (!ratingPaperId && !showCalibration && !showGuide && phase === "done" && paper) {
    if (paper.result) {
      return <Report paper={paper} mode={mode} onReset={reset} onRerun={rerunPaper} />;
    }
    if (paper.inventory) {
      return <Inventory paper={paper} onReset={reset} onRate={setRatingPaperId} />;
    }
    if (paper.local_notice) {
      return <LocalNotice notice={paper.local_notice} source={paper.source_label} onReset={reset} />;
    }
  }

  return (
    <div className="page">
      <Header mode={mode} />
      <main className="container">
        {ratingPaperId ? (
          <Rate paperId={ratingPaperId} onExit={() => setRatingPaperId(null)} />
        ) : showCalibration ? (
          <Calibration onExit={() => setShowCalibration(false)} />
        ) : showGuide ? (
          <Guide onExit={() => setShowGuide(false)} />
        ) : (
          phase === "error" && (
            <div className="card error-card">
              <h2>Something went wrong</h2>
              <p>{error}</p>
              <button className="btn" onClick={reset}>
                Try again
              </button>
            </div>
          )
        )}
      </main>
      <Footer
        onGuide={() => setShowGuide(true)}
        onPrivacy={() => setModal("privacy")}
        onCalibration={() => setShowCalibration(true)}
      />
      {modal === "privacy" && (
        <PrivacyModal firstRun={firstRun} onClose={firstRun ? ackPrivacy : () => setModal(null)} />
      )}
    </div>
  );
}

function Header({ mode }: { mode: "full" | "local" }) {
  return (
    <header className="topbar">
      <div className="container topbar-inner">
        <div className="brand">
          <img className="brand-logo" src="/logo.png" alt="Bayesify" />
        </div>
        <span className="brand-tag">Measure your Bayesian Workflow against the gold standard</span>
        <ModeIndicator mode={mode} />
      </div>
    </header>
  );
}

// Always-visible reminder of what the current mode means for the outbound data path (F3). The
// per-paper toggle lives in the upload card; this keeps the privacy consequence on screen at all
// times, including while a report is showing.
function ModeIndicator({ mode }: { mode: "full" | "local" }) {
  if (mode === "local") {
    return (
      <span className="mode-indicator mi-local" title="Detectors only — no LLM call.">
        Local-only · nothing leaves this machine
      </span>
    );
  }
  return (
    <span className="mode-indicator mi-full" title="Extracted text is sent to Anthropic for grading.">
      Full · text sent to Anthropic
    </span>
  );
}

function Footer({
  onGuide,
  onPrivacy,
  onCalibration,
}: {
  onGuide: () => void;
  onPrivacy: () => void;
  onCalibration: () => void;
}) {
  return (
    <footer className="footer">
      <div className="container footer-inner">
        <span>
          Formative report, not a verdict. The badge concept was dropped — Bayesify reports per-step
          practice, not a pass/fail.
        </span>
        <span className="footer-links">
          <button className="link-btn" onClick={onGuide}>
            Guide
          </button>
          <button className="link-btn" onClick={onPrivacy}>
            Privacy
          </button>
          <button className="link-btn" onClick={onCalibration}>
            Calibration
          </button>
        </span>
      </div>
    </footer>
  );
}

