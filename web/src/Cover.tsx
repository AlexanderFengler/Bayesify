import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import { Box, Button, Typography } from "@mui/material";
import { HeroShell } from "./HeroShell";

// The first screen: a full-bleed hero that fronts the slogan and a single call to action. "Get
// Started" hands off to the landing page (upload / analyze). It reuses HeroShell so the brand band,
// wordmark, and animated aurora are identical to every other immersive screen. The cover starts no
// analysis, so it omits the mode chip and lets the header span the full viewport width.
export function Cover({ onGetStarted }: { onGetStarted: () => void }) {
  return (
    <HeroShell>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: { xs: 3, md: 4 },
          py: { xs: 4, md: 8 },
        }}
      >
        <Typography
          variant="h1"
          sx={{
            fontWeight: 700,
            lineHeight: 1.05,
            letterSpacing: "-0.02em",
            fontSize: { xs: "2.25rem", sm: "3rem", md: "3.75rem" },
            maxWidth: 900,
          }}
        >
          Bring your Bayesian workflow to the gold standard
        </Typography>
        <Button
          variant="contained"
          size="large"
          disableElevation
          endIcon={<ArrowForwardIcon />}
          onClick={onGetStarted}
          sx={{
            mt: 1,
            px: 4,
            py: 1.25,
            fontSize: "1.05rem",
            bgcolor: "common.white",
            color: "#103a52",
            "&:hover": { bgcolor: "rgba(255,255,255,0.9)" },
          }}
        >
          Get Started
        </Button>
      </Box>
    </HeroShell>
  );
}
