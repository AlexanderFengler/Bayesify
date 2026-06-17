// A short in-app user guide reached from the footer. Two audiences, two flows: get a paper rated
// (authors/readers) and rate a paper blind (domain experts, the calibration gold standard).
export function Guide({ onExit }: { onExit: () => void }) {
  return (
    <div className="report guide">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">Guide</div>
          <h1 className="report-title">How VeriBayes works</h1>
        </div>
        <button className="btn" onClick={onExit}>
          Back
        </button>
      </div>

      <p className="guide-intro">
        VeriBayes checks how well a paper follows the <strong>Bayesian workflow</strong> &mdash; model
        specification, priors, predictive checks, convergence diagnostics, and so on &mdash; against a
        rubric of community best practices, with every finding grounded in the paper and in the
        methodological literature. Scores are <strong>formative, not a verdict</strong>. There are two
        ways to use it.
      </p>

      <section className="card guide-section">
        <h2 className="guide-h">Get your paper rated</h2>
        <p className="guide-lead">
          For authors and readers &mdash; an evidence-linked, per-step report on a paper.
        </p>
        <ol className="guide-steps">
          <li>
            <strong>Add the paper.</strong> Drop a PDF, or paste an identifier (arXiv ID, DOI,
            OpenAlex ID, or URL) and VeriBayes fetches the open-access copy.
          </li>
          <li>
            <strong>Pick a mode.</strong> <em>Full</em> sends the extracted text to Anthropic and
            returns the graded report; <em>Local-only</em> runs the on-device detectors with nothing
            leaving your machine (an evidence inventory, no scores).
          </li>
          <li>
            <strong>Click Analyze.</strong> You get a dashboard &mdash; the steps at a glance plus a
            coverage and a quality score (hover the &#9432; for exactly how each is computed) &mdash;
            then the <strong>Full report</strong>: per step, what was done well, concrete suggestions,
            and the supporting quotes &ldquo;in the paper&rdquo;.
          </li>
          <li>
            <strong>Read the summary.</strong> The end of the report recaps the result and lists the
            priority fixes, ranked by impact.
          </li>
          <li>
            <strong>Edge cases.</strong> If the paper isn&rsquo;t a Bayesian application &mdash; e.g. a
            review or opinion piece &mdash; the rubric doesn&rsquo;t directly apply and nothing is
            graded; you can still &ldquo;Run full assessment anyway&rdquo;. Disagree with a step? Use{" "}
            <em>Disagree?</em> to record a correction. Download the report as JSON or Markdown anytime.
          </li>
        </ol>
      </section>

      <section className="card guide-section">
        <h2 className="guide-h">Rate a paper (blind)</h2>
        <p className="guide-lead">
          For domain experts &mdash; your ratings are the gold standard the engine is measured against.
          You rate <strong>blind</strong> (you never see the engine&rsquo;s verdict), so your judgment
          isn&rsquo;t anchored to it.
        </p>
        <ol className="guide-steps">
          <li>
            <strong>Open the blind form.</strong> On the landing page click{" "}
            <em>Rate it yourself (blind)</em>, or open a <code>?rate=&hellip;</code> link you were
            assigned. The paper is ingested on-device (detectors only, no LLM).
          </li>
          <li>
            <strong>You see the rubric and the evidence.</strong> The steps to walk and the raw
            detected spans (where the engine looked) &mdash; never the engine&rsquo;s grades.
          </li>
          <li>
            <strong>Judge each step.</strong> Mark whether it applies, its status (done well / partial
            / missing / N/A), your confidence, a one-line rationale, and cite the relevant quotes.
          </li>
          <li>
            <strong>Submit.</strong> Your rating is stored durably. When several experts rate the same
            paper, their ratings are combined into a consensus that drives the{" "}
            <strong>Calibration</strong> page (engine-vs-expert agreement).
          </li>
        </ol>
      </section>

      <p className="guide-foot">
        VeriBayes runs locally and is honest about its limits: the engine is not yet validated against
        expert ratings &mdash; which is exactly what blind rating contributes to. See the{" "}
        <strong>Calibration</strong> link in the footer for the current agreement metrics.
      </p>
    </div>
  );
}
