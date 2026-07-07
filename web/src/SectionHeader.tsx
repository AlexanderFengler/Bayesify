import { Box, Typography } from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";

// The main page's type scale, from the hero down. Sizes are negotiated so each tier reads a clear
// step apart from its neighbours (weight alone doesn't carry the hierarchy):
//   hero headline 3.5rem → section title 2.25rem → subsection 1.4rem → step label 1.05rem →
//   body 0.9rem → micro (caps overlines, step ids) ≤0.75rem.
// SectionHeader renders the section tier; SubsectionTitle the tier below it.

// A subsection heading ("Get your paper rated", "How they differ", "Privacy & data handling"):
// the tier between the section titles and the step labels.
export function SubsectionTitle({ children, sx }: { children: React.ReactNode; sx?: SxProps<Theme> }) {
  return (
    <Typography
      component="h4"
      sx={[
        { fontWeight: 700, lineHeight: 1.3, fontSize: { xs: "1.2rem", md: "1.4rem" }, letterSpacing: "-0.01em" },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {children}
    </Typography>
  );
}

// The shared heading block for the main page's sections ("How it works", "The rubrics"): the
// section title and its full-width lead. One component so both sections sit on the same tier of
// the page's type scale — a full step below the hero headline, a full step above the subsection
// headings ("Get your paper rated", "How they differ", …).
export function SectionHeader({
  title,
  lead,
  leadMaxWidth = 1520,
}: {
  title: string;
  lead: React.ReactNode;
  leadMaxWidth?: number;
}) {
  return (
    <Box sx={{ mb: { xs: 4, md: 6 } }}>
      <Typography
        variant="h3"
        sx={{
          fontWeight: 700,
          letterSpacing: "-0.02em",
          lineHeight: 1.15,
          fontSize: { xs: "1.75rem", sm: "2rem", md: "2.25rem" },
        }}
      >
        {title}
      </Typography>
      <Typography
        sx={{ mt: 1.5, color: "text.secondary", maxWidth: leadMaxWidth, fontSize: { md: "1.05rem" }, lineHeight: 1.6 }}
      >
        {lead}
      </Typography>
    </Box>
  );
}
