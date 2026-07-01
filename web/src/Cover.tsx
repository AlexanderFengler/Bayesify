import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import { Box, ButtonBase, Typography } from "@mui/material";
import { GoldText } from "./GoldText";
import { HeroShell } from "./HeroShell";

// The first screen: a full-bleed hero that fronts the slogan and a single call to action. "Get
// started" hands off to the landing page (upload / analyze). It reuses HeroShell so the brand band,
// wordmark, and animated aurora are identical to every other immersive screen.
export function Cover({ onGetStarted }: { onGetStarted: () => void }) {
  return (
    <HeroShell>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: { xs: 4, md: 5 },
          py: { xs: 4, md: 8 },
        }}
      >
        <Typography
          variant="h1"
          sx={{
            fontWeight: 700,
            lineHeight: 1.08,
            letterSpacing: "-0.02em",
            fontSize: { xs: "2.25rem", sm: "3rem", md: "3.75rem" },
          }}
        >
          {/* always two lines */}
          Bring your Bayesian workflow
          <br />
          to the <GoldText>gold standard</GoldText>
        </Typography>

        <GetStarted onClick={onGetStarted} />
      </Box>
    </HeroShell>
  );
}

// "Get started" as plain text, followed by a forward arrow centered in a solid white circle.
function GetStarted({ onClick }: { onClick: () => void }) {
  return (
    <ButtonBase
      onClick={onClick}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 1.5,
        borderRadius: 999,
        py: 0.5,
        "&:hover .cta-circle": { transform: "translateX(3px)" },
      }}
    >
      <Typography sx={{ fontWeight: 600, fontSize: "1.15rem", color: "text.primary" }}>
        Get started
      </Typography>
      <Box
        className="cta-circle"
        sx={{
          width: 46,
          height: 46,
          borderRadius: "50%",
          bgcolor: "primary.main",
          color: "primary.contrastText",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "transform 160ms ease",
        }}
      >
        <ArrowForwardIcon />
      </Box>
    </ButtonBase>
  );
}
