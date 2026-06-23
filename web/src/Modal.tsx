import { useEffect } from "react";

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
          document to the configured LLM provider. Nothing else leaves the
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
        Submitting an identifier (arXiv/DOI/OpenAlex/URL) instead of a file fetches its open-access
        PDF &mdash; which reveals to that provider which paper you&rsquo;re looking up.
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
