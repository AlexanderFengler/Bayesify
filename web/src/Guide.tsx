import { Box, Button, Container, Paper, Typography } from "@mui/material";
import { TopBar } from "./HeroShell";

// A short in-app user guide reached from the footer. Two audiences, two flows: get a paper rated
// (authors/readers) and rate a paper blind (domain experts, the calibration gold standard).
export function Guide({ mode, onExit }: { mode: "full" | "local"; onExit: () => void }) {
  return (
    <Box sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column", bgcolor: "background.default" }}>
      <TopBar mode={mode} />
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="md" sx={{ py: { xs: 3, md: 5 } }}>
          <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
            <Box>
              <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.08em" }}>
                Guide
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
                How Bayesify works
              </Typography>
            </Box>
            <Button variant="outlined" onClick={onExit} sx={{ flexShrink: 0 }}>
              Back
            </Button>
          </Box>

          <Typography sx={{ mt: 2.5, color: "text.secondary" }}>
            Bayesify checks how well a paper follows the <strong>Bayesian workflow</strong> &mdash;
            model specification, priors, predictive checks, convergence diagnostics, and so on &mdash;
            against a rubric of community best practices, with every finding grounded in the paper and
            in the methodological literature. Scores are <strong>formative, not a verdict</strong>.
            There are two ways to use it.
          </Typography>

          <GuideSection title="Get your paper rated" lead="For authors and readers — an evidence-linked, per-step report on a paper.">
            <GuideStep n={1} head="Add the paper.">
              Drop a PDF, or paste an identifier (arXiv ID, DOI, OpenAlex ID, or URL) and Bayesify
              fetches the open-access copy.
            </GuideStep>
            <GuideStep n={2} head="Pick a mode.">
              <em>Full</em> sends the extracted text to Anthropic and returns the graded report;{" "}
              <em>Local-only</em> runs the on-device detectors with nothing leaving your machine (an
              evidence inventory, no scores).
            </GuideStep>
            <GuideStep n={3} head="Click Analyze.">
              You get a dashboard &mdash; the steps at a glance plus a coverage and a quality score
              (hover the &#9432; for exactly how each is computed) &mdash; then the{" "}
              <strong>Full report</strong>: per step, what was done well, concrete suggestions, and
              the supporting quotes &ldquo;in the paper&rdquo;.
            </GuideStep>
            <GuideStep n={4} head="Read the summary.">
              The end of the report recaps the result and lists the priority fixes, ranked by impact.
            </GuideStep>
            <GuideStep n={5} head="Edge cases.">
              If the paper isn&rsquo;t a Bayesian application &mdash; e.g. a review or opinion piece
              &mdash; the rubric doesn&rsquo;t directly apply and nothing is graded; you can still
              &ldquo;Run full assessment anyway&rdquo;. Disagree with a step? Use <em>Disagree?</em> to
              record a correction. Download the report as JSON or Markdown anytime.
            </GuideStep>
          </GuideSection>

          <GuideSection
            title="Rate a paper (blind)"
            lead="For domain experts — your ratings are the gold standard the engine is measured against. You rate blind (you never see the engine's verdict), so your judgment isn't anchored to it."
          >
            <GuideStep n={1} head="Open the blind form.">
              On the landing page click <em>Rate it yourself (blind)</em>, or open a{" "}
              <code>/rate/&hellip;</code> link you were assigned. The paper is ingested on-device
              (detectors only, no LLM).
            </GuideStep>
            <GuideStep n={2} head="You see the rubric and the evidence.">
              The steps to walk and the raw detected spans (where the engine looked) &mdash; never the
              engine&rsquo;s grades.
            </GuideStep>
            <GuideStep n={3} head="Judge each step.">
              Mark whether it applies, its status (done well / partial / missing / N/A), your
              confidence, a one-line rationale, and cite the relevant quotes.
            </GuideStep>
            <GuideStep n={4} head="Submit.">
              Your rating is stored durably. When several experts rate the same paper, their ratings
              are combined into a consensus that drives the <strong>Calibration</strong> page
              (engine-vs-expert agreement).
            </GuideStep>
          </GuideSection>

          <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>
            Bayesify runs locally and is honest about its limits: the engine is not yet validated
            against expert ratings &mdash; which is exactly what blind rating contributes to. See the{" "}
            <strong>Calibration</strong> link for the current agreement metrics.
          </Typography>
        </Container>
      </Box>
    </Box>
  );
}

function GuideSection({
  title,
  lead,
  children,
}: {
  title: string;
  lead: string;
  children: React.ReactNode;
}) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 3, mt: 2.5 }}>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {lead}
      </Typography>
      <Box component="ol" sx={{ listStyle: "none", p: 0, m: 0, mt: 2, display: "flex", flexDirection: "column", gap: 1.5 }}>
        {children}
      </Box>
    </Paper>
  );
}

function GuideStep({ n, head, children }: { n: number; head: string; children: React.ReactNode }) {
  return (
    <Box component="li" sx={{ display: "flex", gap: 1.5 }}>
      <Box
        sx={{
          flexShrink: 0,
          width: 24,
          height: 24,
          borderRadius: "50%",
          bgcolor: "primary.light",
          color: "primary.main",
          fontSize: "0.8rem",
          fontWeight: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {n}
      </Box>
      <Typography variant="body2">
        <strong>{head}</strong> {children}
      </Typography>
    </Box>
  );
}
