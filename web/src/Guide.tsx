import { Box, Button, Container, TextField, Typography } from "@mui/material";
import { useState } from "react";

import { getReviewerToken, setReviewerToken } from "./api";

// A short in-app explainer reached from the footer. Two audiences, two flows shown side by side:
// get a paper rated (authors/readers) and rate a paper blind (domain experts, the gold standard).
export function Guide() {
  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
            How it works
          </Typography>
          <Typography sx={{ mt: 1.5, color: "text.secondary", maxWidth: 1520 }}>
            Bayesify checks how well a paper follows a <strong>Bayesian workflow</strong> &mdash;
            model specification, priors, predictive checks, convergence diagnostics, and so on &mdash;
            against a rubric of community best practices, with every finding grounded in the paper and
            in the methodological literature. Scores are <strong>formative, not a verdict</strong>.
            There are two ways to use it.
          </Typography>
        </Box>
      </Box>

      {/* the two flows, side by side (stacked on phones), free of boxes */}
      <Box
        sx={{
          mt: { xs: 3, md: 5 },
          display: "flex",
          flexDirection: { xs: "column", md: "row" },
          gap: { xs: 4, md: 8 },
          alignItems: "flex-start",
        }}
      >
        <GuideColumn title="Get your paper rated" lead="For authors and readers: an evidence-linked, per-step report on a paper.">
          <GuideStep n={1} head="Add the paper.">
            Drop a PDF, or paste an identifier (arXiv ID, DOI, OpenAlex ID, or URL) and Bayesify
            fetches the open-access copy.
          </GuideStep>
          <GuideStep n={2} head="Select a rubric.">
            There is no standard Bayesian workflow. Select among existing <em>rubrics</em> emobdying different workflow philosophies.{" "}
          </GuideStep>
          <GuideStep n={3} head="Click 'Analyze'.">
            You get a dashboard &mdash; the steps at a glance plus a coverage and a quality score
            (hover the &#9432; for exactly how each is computed) &mdash; then the{" "}
            <strong>Full report</strong>: per step, what was adequate, concrete suggestions, and the
            supporting quotes &ldquo;in the paper&rdquo;.
          </GuideStep>
          <GuideStep n={4} head="Read the summary.">
            The end of the report recaps the result and lists the priority fixes, ranked by impact.
          </GuideStep>
          <GuideStep n={5} head="Edge cases.">
            If the paper isn&rsquo;t a Bayesian application (e.g. a review or opinion piece), 
            the rubric doesn&rsquo;t directly apply and nothing is graded; you can still
            &ldquo;run full assessment anyway&rdquo;. Download the report as JSON or Markdown anytime.
          </GuideStep>
        </GuideColumn>

        <GuideColumn
          title="Rate a paper (blind)"
          lead="For domain experts: your ratings are the gold standard the engine will be measured against. You rate blind (you never see the engine's verdict), so your judgment isn't anchored to it."
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
            Mark whether it applies, its status (adequate / partial / missing / N/A), your
            confidence, a one-line rationale, and cite the relevant quotes.
          </GuideStep>
          <GuideStep n={4} head="Submit.">
            Your rating is stored durably. When several experts rate the same paper, their ratings are
            combined into a consensus that drives the <strong>Calibration</strong> page
            (engine-vs-expert agreement).
          </GuideStep>
        </GuideColumn>
      </Box>

      <PrivacySection />

      <ReviewerTokenField />
    </Container>
  );
}

// What is and isn't kept. The source manuscript is never stored — only the graded report is saved
// (to the database), which is what makes the Archive browsable. Absorbs the plain-spoken data-path
// wording from the old privacy dialog: what leaves the machine, and the two caveats worth knowing.
function PrivacySection() {
  return (
    <Box sx={{ mt: { xs: 4, md: 6 }, maxWidth: 1520 }}>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        Privacy &amp; data handling
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        <strong>Your paper is not saved.</strong> To make its per-step judgments, Bayesify sends the{" "}
        <strong>extracted text</strong> of your document to the configured LLM provider — nothing else
        leaves the machine: not the PDF file, not your identity. The uploaded file is used only to run
        the analysis and is then discarded.
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
        <strong>Only the report is stored.</strong> The graded assessment is saved to the database so
        you can reopen it and browse it in the <strong>Archive</strong>. The source manuscript itself
        is never kept.
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
        If a manuscript is confidential or embargoed, treat this as &ldquo;this text will be sent to a
        third-party API for processing&rdquo; and decide accordingly. Submitting an identifier
        (arXiv/DOI/OpenAlex/URL) instead of a file fetches its open-access PDF — which reveals to that
        provider which paper you&rsquo;re looking up.
      </Typography>
    </Box>
  );
}

// Trusted-reviewer token: a shared secret that promotes this browser's "Disagree?" corrections to
// trusted ones, which enter the global override bank and can adjust grading on similar papers.
function ReviewerTokenField() {
  const [token, setToken] = useState(getReviewerToken());
  const [saved, setSaved] = useState(false);
  return (
    <Box sx={{ mt: { xs: 4, md: 5 }, p: 2, borderRadius: 2, bgcolor: "action.hover" }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        Trusted reviewer token
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        If you&rsquo;re a trusted reviewer, paste your shared-secret token. Your comments on the reports then become trusted &mdash; they enter the global override bank and can adjust how
        similar steps are graded on other papers. Stored in this browser only.
      </Typography>
      <Box sx={{ display: "flex", gap: 1, mt: 1.5, alignItems: "center", flexWrap: "wrap" }}>
        <TextField
          size="small"
          type="password"
          placeholder="reviewer token"
          value={token}
          onChange={(e) => {
            setToken(e.target.value);
            setSaved(false);
          }}
          sx={{ minWidth: 240 }}
        />
        <Button
          variant="outlined"
          onClick={() => {
            setReviewerToken(token.trim());
            setSaved(true);
          }}
        >
          Save
        </Button>
        {token && (
          <Button
            color="inherit"
            onClick={() => {
              setToken("");
              setReviewerToken("");
              setSaved(false);
            }}
          >
            Clear
          </Button>
        )}
        {saved && (
          <Typography variant="caption" color="success.main">
            saved to this browser
          </Typography>
        )}
      </Box>
    </Box>
  );
}

export function GuideColumn({
  title,
  lead,
  children,
}: {
  title: string;
  lead: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ flex: "1 1 0", minWidth: 0 }}>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {lead}
      </Typography>
      <Box component="ol" sx={{ listStyle: "none", p: 0, m: 0, mt: 2.5, display: "flex", flexDirection: "column", gap: 2 }}>
        {children}
      </Box>
    </Box>
  );
}

export function GuideStep({ n, head, children }: { n: number; head: string; children: React.ReactNode }) {
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

