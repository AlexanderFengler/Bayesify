import { useEffect, useState } from "react";
import { getCalibration, type Calibration } from "./api";

// A bare overlay + card with a title and a close affordance. Escape and backdrop-click both close.
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 className="modal-title">{title}</h2>
          <button className="modal-x" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

// First-run disclosure + reusable privacy explainer (PRIVACY.md is the source of truth). States the
// outbound data path for each mode plainly, since authors upload unpublished manuscripts.
export function PrivacyModal({ onClose, firstRun }: { onClose: () => void; firstRun?: boolean }) {
  return (
    <Modal title={firstRun ? "Before you start" : "Privacy & data handling"} onClose={onClose}>
      <p className="modal-lead">
        VeriBayes is <strong>local-first</strong>: storage stays on this machine, there is no
        account, and no telemetry. There are two analysis modes, chosen per paper.
      </p>

      <div className="privacy-mode">
        <div className="privacy-mode-head pm-full">Full mode</div>
        <p>
          To make per-step judgments, VeriBayes sends the <strong>extracted text</strong> of your
          document to Anthropic (via your Claude subscription or API key). Nothing else leaves the
          machine — not the PDF file, not your identity, not the results. If a manuscript is
          confidential or embargoed, treat this as &ldquo;this text will be sent to a third-party API
          for processing&rdquo; and decide accordingly.
        </p>
      </div>

      <div className="privacy-mode">
        <div className="privacy-mode-head pm-local">Local-only mode</div>
        <p>
          <strong>Nothing leaves this machine.</strong> Local-only runs the parser and the
          deterministic detectors only — no LLM call, no text sent anywhere. It produces an evidence
          inventory (what was found and where), <strong>not a graded report</strong>: there are no
          coverage or quality scores, because scoring requires the model&rsquo;s judgment.
        </p>
      </div>

      <p className="modal-foot">
        Submitting an identifier (arXiv/DOI/OpenAlex/URL) instead of a file reveals which paper you
        are looking up to that open-access provider. Deleting a paper purges everything derived from
        it.
      </p>

      {firstRun && (
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={onClose}>
            Got it
          </button>
        </div>
      )}
    </Modal>
  );
}

// Calibration view — honest about the engine not being validated yet. Pre-M7 there are no agreement
// metrics; this renders that plainly rather than implying an accuracy it cannot back up.
export function CalibrationModal({ onClose }: { onClose: () => void }) {
  const [cal, setCal] = useState<Calibration | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getCalibration()
      .then(setCal)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const validated = cal != null && cal.status !== "not_yet_validated";
  return (
    <Modal title="Calibration" onClose={onClose}>
      {err && <p className="modal-lead">Could not load calibration: {err}</p>}
      {!err && cal == null && <p className="modal-lead">Loading…</p>}
      {cal != null && (
        <>
          <div className={"calib-status " + (validated ? "ok" : "pending")}>
            {validated ? "Validated" : "Not yet validated"}
          </div>
          <p className="modal-lead">{cal.note}</p>
          {!validated && (
            <p className="modal-foot">
              Coverage and quality scores are produced today, but they have not been checked against
              expert ratings. Until the validation run (M7) reports agreement metrics, treat every
              report as <strong>formative, not a verdict</strong>.
            </p>
          )}
          {validated && cal.agreement && (
            <ul className="calib-metrics">
              {Object.entries(cal.agreement).map(([k, v]) => (
                <li key={k}>
                  <span className="calib-k">{k}</span>
                  <span className="calib-v">{v}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Modal>
  );
}
