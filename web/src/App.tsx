import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRubrics, getPaper, rerun, type RubricSummary, streamProgress, submitPaper } from "./api";
import { Calibration } from "./Calibration";
import { Guide } from "./Guide";
import { Inventory } from "./Inventory";
import { PrivacyModal } from "./Modal";
import { Rate } from "./Rate";
import { Report } from "./Report";
import { LOCAL_STAGES, STAGES, type PaperState } from "./types";

type Phase = "idle" | "running" | "done" | "error";
type ModalKind = "privacy" | null;
const PRIVACY_ACK_KEY = "veribayes.privacy.ack"; // set once the first-run disclosure is acknowledged

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
          <>
            {phase === "idle" && (
              <UploadCard
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
              />
            )}
            {phase === "running" && (
              <Progress
                stageState={stageState}
                stages={
                  // an identifier job fetches instead of ingesting an upload → swap the first step
                  !file && identifier.trim()
                    ? ["fetch", ...(mode === "local" ? LOCAL_STAGES : STAGES).slice(1)]
                    : mode === "local"
                      ? LOCAL_STAGES
                      : STAGES
                }
                source={file?.name ?? identifier}
              />
            )}
            {phase === "error" && (
              <div className="card error-card">
                <h2>Something went wrong</h2>
                <p>{error}</p>
                <button className="btn" onClick={reset}>
                  Try again
                </button>
              </div>
            )}
            {phase === "done" && paper?.result && (
              <Report paper={paper} onReset={reset} onRerun={rerunPaper} />
            )}
            {phase === "done" && paper && !paper.result && paper.inventory && (
              <Inventory paper={paper} onReset={reset} onRate={setRatingPaperId} />
            )}
            {phase === "done" && paper && !paper.result && !paper.inventory && paper.local_notice && (
              <LocalNotice notice={paper.local_notice} source={paper.source_label} onReset={reset} />
            )}
          </>
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
          <img className="brand-logo" src="/logo.png" alt="VeriBayes" />
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
          Formative report, not a verdict. The badge concept was dropped — VeriBayes reports per-step
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

interface UploadProps {
  mode: "full" | "local";
  setMode: (m: "full" | "local") => void;
  profile: string;
  setProfile: (p: string) => void;
  rubrics: RubricSummary[];
  identifier: string;
  setIdentifier: (s: string) => void;
  file: File | null;
  setFile: (f: File | null) => void;
  dragging: boolean;
  setDragging: (b: boolean) => void;
  fileInput: React.RefObject<HTMLInputElement>;
  onStart: (intent?: "analyze" | "rate") => void;
}

function UploadCard(p: UploadProps) {
  const canStart = !!p.file || p.identifier.trim().length > 0;
  return (
    <div className="card upload">
      <h1 className="lead">How well does this paper follow the Bayesian workflow?</h1>
      <p className="sub">
        Drop a PDF or paste an identifier. You&rsquo;ll get a per-step report with a coverage and a
        quality score — every finding grounded in the paper and in the methodological literature.
      </p>

      <div
        className={"dropzone" + (p.dragging ? " dragging" : "") + (p.file ? " has-file" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          p.setDragging(true);
        }}
        onDragLeave={() => p.setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          p.setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) p.setFile(f);
        }}
        onClick={() => p.fileInput.current?.click()}
      >
        <input
          ref={p.fileInput}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => p.setFile(e.target.files?.[0] ?? null)}
        />
        {p.file ? (
          <div className="dropzone-file">
            <span className="file-icon">PDF</span>
            <span className="file-name">{p.file.name}</span>
            <button
              className="link-btn"
              onClick={(e) => {
                e.stopPropagation();
                p.setFile(null);
              }}
            >
              remove
            </button>
          </div>
        ) : (
          <>
            <div className="dropzone-icon">⬆</div>
            <div className="dropzone-title">Drop a PDF here</div>
            <div className="dropzone-hint">or click to choose a file</div>
          </>
        )}
      </div>

      <div className="or-row">
        <span className="or-line" />
        <span className="or-text">or paste an identifier</span>
        <span className="or-line" />
      </div>

      <input
        className="text-input"
        placeholder="arXiv ID, DOI, OpenAlex ID, or URL"
        value={p.identifier}
        onChange={(e) => p.setIdentifier(e.target.value)}
        disabled={!!p.file}
      />

      <div className="rubric-select">
        <label>
          Rubric
          <select value={p.profile} onChange={(e) => p.setProfile(e.target.value)}>
            {(p.rubrics.length ? p.rubrics : [{ id: p.profile, label: p.profile }]).map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        {p.rubrics.find((r) => r.id === p.profile)?.summary && (
          <p className="rubric-preamble">{p.rubrics.find((r) => r.id === p.profile)?.summary}</p>
        )}
      </div>

      <div className="controls">
        <ModeToggle mode={p.mode} setMode={p.setMode} />
        <div className="start-actions">
          <button
            className="link-btn rate-cta"
            disabled={!canStart}
            title="Rate this paper yourself against the rubric, blind to the engine's verdict"
            onClick={() => p.onStart("rate")}
          >
            Rate it yourself (blind)
          </button>
          <button className="btn btn-primary" disabled={!canStart} onClick={() => p.onStart("analyze")}>
            Analyze
          </button>
        </div>
      </div>
    </div>
  );
}

function ModeToggle({ mode, setMode }: { mode: "full" | "local"; setMode: (m: "full" | "local") => void }) {
  return (
    <div className="mode" role="group" aria-label="analysis mode">
      <button
        className={"mode-btn" + (mode === "full" ? " active" : "")}
        onClick={() => setMode("full")}
        title="LLM judgment + deterministic checks. Extracted text is sent to the model."
      >
        Full
      </button>
      <button
        className={"mode-btn" + (mode === "local" ? " active" : "")}
        onClick={() => setMode("local")}
        title="Detectors only — no LLM, no scores. Nothing leaves the machine."
      >
        Local-only
      </button>
    </div>
  );
}

function Progress({
  stageState,
  stages,
  source,
}: {
  stageState: Record<string, "running" | "done">;
  stages: readonly string[];
  source?: string;
}) {
  return (
    <div className="card progress-card">
      <h2 className="progress-title">Analyzing</h2>
      {source && <p className="progress-source">{source}</p>}
      <ol className="stepper">
        {stages.map((stage) => {
          const state = stageState[stage];
          return (
            <li key={stage} className={"step " + (state ?? "pending")}>
              <span className="step-dot" />
              <span className="step-label">{stage}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function LocalNotice({
  notice,
  source,
  onReset,
}: {
  notice: string;
  source: string;
  onReset: () => void;
}) {
  return (
    <div className="card local-notice">
      <div className="local-badge">No analysis run yet</div>
      <h2>{source}</h2>
      <p>{notice}</p>
      <button className="btn" onClick={onReset}>
        Analyze another
      </button>
    </div>
  );
}
