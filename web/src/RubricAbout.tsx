import { Box, Typography } from "@mui/material";
import type { Rubric } from "./rubric";

// The rubric explanation shown at the top of the report and under the landing-page picker. It names
// every step explicitly so the "S1, S2, …" labels in the at-a-glance strip have real names attached
// (otherwise readers see only the bare codes). `showHeader` adds the same small-caps section header
// the report uses for "Steps at a glance"; the landing page omits it (it already has a "Rubric" label).
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
      {rubric.steps.length > 0 && (
        <Box
          component="ol"
          sx={{
            listStyle: "none",
            p: 0,
            mt: 1.5,
            mb: 0,
            display: "flex",
            flexDirection: "column",
            gap: 0.75,
          }}
        >
          {rubric.steps.map((s) => (
            <Box component="li" key={s.id} sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
              <Typography
                component="span"
                sx={{ fontFamily: (t) => t.tokens.mono, fontSize: 12, fontWeight: 600, color: "text.disabled", flexShrink: 0 }}
              >
                {s.id}
              </Typography>
              <Typography component="span" variant="body2">
                {s.name}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
