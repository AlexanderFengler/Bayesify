import { useCallback, useRef, useState } from "react";
import { getPaper, streamProgress, submitPaper } from "./api";
import { Report } from "./Report";
import { STAGES, type PaperState, type Stage } from "./types";

type Phase = "idle" | "running" | "done" | "error";

export function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<"full" | "local">("full");
  const [identifier, setIdentifier] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stageState, setStageState] = useState<Record<string, "running" | "done">>({});
  const [paper, setPaper] = useState<PaperState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const reset = () => {
    setPhase("idle");
    setIdentifier("");
    setFile(null);
    setStageState({});
    setPaper(null);
    setError(null);
  };

  const start = useCallback(async () => {
    if (!file && !identifier.trim()) return;
    setPhase("running");
    setStageState({});
    setError(null);
    try {
      const paperId = await submitPaper({ file, identifier, mode });
      streamProgress(
        paperId,
        (e) => {
          if (e.type === "stage" && e.stage) {
            setStageState((prev) => ({ ...prev, [e.stage!]: e.state ?? "running" }));
          }
        },
        async () => {
          const result = await getPaper(paperId);
          setPaper(result);
          setPhase(result.status === "failed" ? "error" : "done");
          if (result.status === "failed") setError(result.error ?? "assessment failed");
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase("error");
    }
  }, [file, identifier, mode]);

  return (
    <div className="page">
      <Header />
      <main className="container">
        {phase === "idle" && (
          <UploadCard
            mode={mode}
            setMode={setMode}
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
        {phase === "running" && <Progress stageState={stageState} source={file?.name ?? identifier} />}
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
          <Report paper={paper} onReset={reset} />
        )}
      </main>
      <Footer />
    </div>
  );
}

function Header() {
  return (
    <header className="topbar">
      <div className="container topbar-inner">
        <div className="brand">
          <span className="brand-mark">β</span>
          <span className="brand-name">VeriBayes</span>
        </div>
        <span className="brand-tag">Bayesian-workflow report</span>
        <span className="pill pill-stub" title="The engine is a stub at this milestone.">
          M1 · stub engine
        </span>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        Formative report, not a verdict. The badge concept was dropped — VeriBayes reports per-step
        practice, not a pass/fail.
      </div>
    </footer>
  );
}

interface UploadProps {
  mode: "full" | "local";
  setMode: (m: "full" | "local") => void;
  identifier: string;
  setIdentifier: (s: string) => void;
  file: File | null;
  setFile: (f: File | null) => void;
  dragging: boolean;
  setDragging: (b: boolean) => void;
  fileInput: React.RefObject<HTMLInputElement>;
  onStart: () => void;
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

      <div className="controls">
        <ModeToggle mode={p.mode} setMode={p.setMode} />
        <button className="btn btn-primary" disabled={!canStart} onClick={p.onStart}>
          Analyze
        </button>
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

function Progress({ stageState, source }: { stageState: Record<string, "running" | "done">; source?: string }) {
  return (
    <div className="card progress-card">
      <h2 className="progress-title">Analyzing</h2>
      {source && <p className="progress-source">{source}</p>}
      <ol className="stepper">
        {STAGES.map((stage: Stage) => {
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
