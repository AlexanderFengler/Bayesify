import {
  Box,
  Button,
  Container,
  Paper,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { useState } from "react";

import { getReviewerToken, setReviewerToken } from "./api";
import { SectionHeader, SubsectionTitle } from "./SectionHeader";

// One step of a flow diagram: the short label on the step node and the explanatory body under it.
type FlowStep = { head: string; body: React.ReactNode };

// Flow 1 — get a paper rated (authors/readers): an evidence-linked, per-step report on a paper.
const GET_RATED_STEPS: FlowStep[] = [
  {
    head: "Add the paper",
    body: (
      <>
        Drop a PDF, or paste an identifier (arXiv ID, DOI, OpenAlex ID, or URL) and Bayesify 
        will try to fetch the open-access copy.
      </>
    ),
  },
  {
    head: "Click Analyze",
    body: (
      <>
        The paper goes through our multi-stage pipeline and you get a step-by-step coverage report with 
        suggestions and adversarial checks.
      </>
    ),
  },
  {
    head: "Read the summary",
    body: <>The end of the report recaps the result and lists the priority fixes, ranked by impact.</>,
  },
  {
    head: "Edge cases",
    body: (
      <>
        If the paper isn&rsquo;t about Bayesian methodology, the rubric doesn&rsquo;t directly apply 
        and nothing is graded.
      </>
    ),
  },
];

// Flow 2 — rate a paper blind (domain experts): the gold standard the engine is measured against.
const RATE_BLIND_STEPS: FlowStep[] = [
  {
    head: "Open the blind form",
    body: (
      <>
        As before, upload a paper, select <em>Human Expert</em>, then click <em>Rate it yourself</em>.
      </>
    ),
  },
  {
    head: "See the rubric & evidence",
    body: (
      <>
        The steps to grade and the raw detected spans (what our parsers extracted).
      </>
    ),
  },
  {
    head: "Judge each step",
    body: (
      <>
        Mark whether it applies, its status, your confidence, a
        one-line rationale, and the relevant quotes.
      </>
    ),
  },
  {
    head: "Submit",
    body: (
      <>
        Your rating is stored durably and anonymously. Expert ratings will eventually drive the calibration of our engine.
      </>
    ),
  },
];

// The "How it works" explainer — a full-height section of the main page (anchored by `id`), sized
// like the hero so it owns its own screenful. Two audiences, two flows rendered as step diagrams:
// get a paper rated (authors/readers) and rate a paper blind (domain experts, the gold standard).
export function Guide({ id }: { id?: string }) {
  return (
    <Container
      id={id}
      maxWidth="xl"
      sx={{
        py: { xs: 6, md: 8 },
        // fill the viewport between header and footer, like the hero (100cqh: the scroll area is a
        // size query container); centre the content when it runs shorter than that
        minHeight: "calc(100dvh - 220px)",
        "@supports (min-height: 100cqh)": { minHeight: "100cqh" },
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <SectionHeader
        title="How it works"
        lead={
          <>
            Bayesify checks how well a paper follows the <strong>Bayesian workflow</strong> (e.g.,
            model specification, priors, predictive checks, convergence diagnostics) against a rubric 
            of community best practices, with every finding grounded in the paper and the rubric. 
            Scores are <strong>formative, not a verdict</strong>.
            There are two ways to use it.
          </>
        }
      />

      {/* the two flows, stacked, each drawn as a stepper diagram */}
      <Box sx={{ display: "flex", flexDirection: "column", gap: { xs: 5, md: 8 } }}>
        <FlowSection
          title="Analyze a paper using our AI agent"
          lead=""
          steps={GET_RATED_STEPS}
        />
        <FlowSection
          title="Rate a paper as a human expert"
          lead=""
          steps={RATE_BLIND_STEPS}
        />
      </Box>

      <PrivacySection />
    </Container>
  );
}

function FlowSection({ title, lead, steps }: { title: string; lead: string; steps: FlowStep[] }) {
  return (
    // Each rating method is a card with the same responsive lift as the rubric columns: it
    // brightens, lifts, and casts a primary-tinted glow on hover.
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2.5, md: 3 },
        borderRadius: 3,
        transition: "transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease",
        "&:hover": {
          transform: { md: "translateY(-6px)" },
          borderColor: "primary.main",
          boxShadow: (t) => `0 14px 36px ${alpha(t.palette.primary.main, 0.22)}`,
        },
      }}
    >
      <SubsectionTitle>{title}</SubsectionTitle>
      {/* subsection captions run full width, one size step under the section lead (0.95 vs 1.05) */}
      <Typography color="text.secondary" sx={{ mt: 0.75, fontSize: "0.95rem", lineHeight: 1.6 }}>
        {lead}
      </Typography>
      <Box sx={{ mt: 3 }}>
        <FlowStepper steps={steps} />
      </Box>
    </Paper>
  );
}

// The flow diagram itself (MUI Stepper). Wide screens draw it horizontally — the numbered nodes and
// their connectors on one line, label and body text left-aligned beneath each node; narrow screens
// draw the classic vertical stepper. Every step is `active` (these are diagrams, not wizards), which
// keeps the numbered nodes in the primary colour.
function FlowStepper({ steps }: { steps: FlowStep[] }) {
  const theme = useTheme();
  const horizontal = useMediaQuery(theme.breakpoints.up("md"));

  // Shared sizing: 32px numbered nodes (a diagram element, not an inline bullet) and step labels a
  // clear size step above the body text — the label/body contrast is size + colour, not just weight.
  const labelSx = {
    fontWeight: 700,
    fontSize: "1.05rem",
    lineHeight: 1.35,
    "&.Mui-active": { fontWeight: 700 },
  };
  const bodySx = { fontSize: "0.9rem", lineHeight: 1.6 };

  if (!horizontal) {
    return (
      <Stepper
        orientation="vertical"
        sx={{
          "& .MuiStepIcon-root": { fontSize: 32 },
          "& .MuiStepLabel-label": labelSx,
          // the vertical rail and the content's guide line re-centre under the 32px node (16px)
          "& .MuiStepConnector-root": { ml: "16px" },
          "& .MuiStepContent-root": { ml: "16px" },
        }}
      >
        {steps.map((s) => (
          <Step key={s.head} active expanded>
            <StepLabel>{s.head}</StepLabel>
            <StepContent>
              <Typography color="text.secondary" sx={bodySx}>
                {s.body}
              </Typography>
            </StepContent>
          </Step>
        ))}
      </Stepper>
    );
  }

  return (
    <Stepper
      alternativeLabel
      sx={{
        alignItems: "flex-start",
        // left-align each step: node at the step's left edge, label and body text under it
        "& .MuiStep-root": { px: 0, pr: 3 },
        "& .MuiStepIcon-root": { fontSize: 32 },
        "& .MuiStepLabel-root": { alignItems: "flex-start" },
        "& .MuiStepLabel-label": {
          ...labelSx,
          textAlign: "left",
          "&.MuiStepLabel-alternativeLabel": { mt: 1.25 },
        },
        // re-aim the connectors at the left-aligned nodes (the defaults assume centred icons):
        // from just after the previous node (icon is 32px wide, centre 16px) to just before this one
        "& .MuiStepConnector-root": { top: 16, left: "calc(-100% + 40px)", right: "calc(100% + 8px)" },
      }}
    >
      {steps.map((s) => (
        <Step key={s.head} active>
          <StepLabel>{s.head}</StepLabel>
          <Typography color="text.secondary" sx={{ ...bodySx, mt: 1 }}>
            {s.body}
          </Typography>
        </Step>
      ))}
    </Stepper>
  );
}

// What is and isn't kept. The source manuscript is never stored — only the graded report is saved
// (to the database), which is what makes the Archive browsable. Absorbs the plain-spoken data-path
// wording from the old privacy dialog: what leaves the machine, and the two caveats worth knowing.
function PrivacySection() {
  return (
    <Box sx={{ mt: { xs: 5, md: 8 } }}>
      <SubsectionTitle>Privacy &amp; data handling</SubsectionTitle>
      {/* full-width paragraphs on the caption tier (0.95rem), like every other subsection body */}
      <Typography color="text.secondary" sx={{ mt: 1.25, fontSize: "0.95rem", lineHeight: 1.6 }}>
        <strong>Your paper is not saved.</strong> To make its per-step judgments, Bayesify sends the{" "}
        <strong>extracted text</strong> of your document to the configured LLM provider — nothing else
        leaves the machine: not the PDF file, not your identity. The uploaded file is used only to run
        the analysis and is then discarded.
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 1.5, fontSize: "0.95rem", lineHeight: 1.6 }}>
        <strong>Only the report is stored.</strong> The graded assessment is saved to the database so
        you can reopen it and browse it in the <strong>Archive</strong>. The source manuscript itself
        is never kept.
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 1.5, fontSize: "0.95rem", lineHeight: 1.6 }}>
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
// Rendered by Landing at the very bottom of the main page (it's plumbing, not pitch).
export function ReviewerTokenField() {
  const [token, setToken] = useState(getReviewerToken());
  const [saved, setSaved] = useState(false);
  return (
    <Box sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 2, bgcolor: "action.hover" }}>
      <SubsectionTitle>Trusted reviewer token</SubsectionTitle>
      <Typography color="text.secondary" sx={{ mt: 0.75, fontSize: "0.95rem", lineHeight: 1.6 }}>
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
