import { Box, Link, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import type { Rubric } from "./rubric";

// The rubric blurb shown under the landing-page picker and atop the report. It no longer spells out
// the full step outline — that lives in the main page's rubrics section now — it gives the one-line
// description and links there. `showHeader` adds the small-caps section header the report uses.
export function RubricAbout({ rubric, showHeader = false }: { rubric: Rubric; showHeader?: boolean }) {
  return (
    <Box>
      {showHeader && (
        <Typography
          variant="caption"
          sx={{ fontWeight: 600, color: "text.secondary", textTransform: "uppercase", letterSpacing: "0.06em" }}
        >
          About this rubric
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mt: showHeader ? 0.5 : 0 }}>
        <strong>{rubric.label}.</strong> {rubric.summary}
      </Typography>
      <Link
        component={RouterLink}
        to="/#rubrics"
        variant="body2"
        underline="hover"
        sx={{ mt: 1, display: "inline-block", fontWeight: 600 }}
      >
        See all rubrics &amp; how they compare →
      </Link>
    </Box>
  );
}
