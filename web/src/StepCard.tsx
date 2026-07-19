import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FormatQuoteIcon from "@mui/icons-material/FormatQuote";
import { Box, ButtonBase, Collapse, Paper, Typography } from "@mui/material";
import { type ReactNode, useState } from "react";
import { MathText } from "./MathText";
import type { EvidenceSpan, StepStatus } from "./types";

// Shared, blind-safe step-card atoms used by BOTH the engine report (Report.tsx) and the blind
// rating form (Rate.tsx). They carry no engine judgment of their own — each consumer passes its own
// pill/header/body in — so the rating form can reuse the layout without inheriting the engine's
// framing (the validity firewall).

// The status-tinted left border — mirrors the report's palette so the two views read alike. An
// unrated/blank step keeps the neutral strong line.
const BORDER_COLOR: Record<StepStatus, string> = {
  adequate: "success.main",
  partial: "warning.main",
  missing: "error.main",
  not_applicable: "divider",
};

// The frame + header (step-id + step-name) with a leading `pill` slot and a trailing `headerRight`
// slot, plus the body as children.
export function StepCardShell({
  stepId,
  stepName,
  status,
  sectionId,
  pill,
  headerRight,
  children,
}: {
  stepId: string;
  stepName: string;
  status?: StepStatus | ""; // tints the left border; "" / undefined = unrated (neutral)
  sectionId?: string;
  pill?: ReactNode;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  const na = status === "not_applicable";
  return (
    <Paper
      id={sectionId}
      component="section"
      variant="outlined"
      sx={{
        p: { xs: 2, md: 2.5 },
        borderRadius: 2,
        borderLeft: "3px solid",
        borderLeftColor: status ? BORDER_COLOR[status] : (t) => t.tokens.lineStrong,
        bgcolor: na ? "action.hover" : "background.paper",
        opacity: status ? 1 : 0.9,
      }}
    >
      <Box component="header" sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
        {pill}
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flex: 1, minWidth: 0 }}>
          <Typography
            component="span"
            sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 12, fontWeight: 600, color: "text.disabled" }}
          >
            {stepId}
          </Typography>
          <Typography component="span" sx={{ fontWeight: 600, fontSize: "0.95rem" }}>
            {stepName}
          </Typography>
        </Box>
        {headerRight}
      </Box>
      {children}
    </Paper>
  );
}

// The "In the paper" evidence panel over verbatim spans — collapsed by default (it's supporting
// detail, not the headline). Renders nothing when empty.
export function EvidenceBlock({ spans, label = "In the paper" }: { spans: EvidenceSpan[]; label?: string }) {
  const [open, setOpen] = useState(false);
  if (spans.length === 0) return null;
  return (
    <Box sx={{ mt: 1 }}>
      <ButtonBase
        onClick={() => setOpen((o) => !o)}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.5,
          fontSize: "0.75rem",
          fontWeight: 600,
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        <ExpandMoreIcon
          fontSize="small"
          sx={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 120ms" }}
        />
        {label} ({spans.length})
      </ButtonBase>
      <Collapse in={open}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
          {spans.map((s, i) => (
            <Box
              key={i}
              component="blockquote"
              sx={{
                m: 0,
                pl: 1.5,
                borderLeft: 2,
                borderColor: "divider",
                fontSize: "0.875rem",
                color: "text.secondary",
              }}
            >
              <FormatQuoteIcon sx={{ fontSize: 14, mr: 0.5, opacity: 0.5, verticalAlign: "middle" }} />
              <MathText>{s.quote}</MathText>
              <Typography
                component="cite"
                variant="caption"
                sx={{ display: "block", mt: 0.25, color: "text.disabled", fontStyle: "normal" }}
              >
                §{s.section_id}
                {s.page != null && `, p.${s.page}`}
              </Typography>
            </Box>
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}
