import { Box } from "@mui/material";

// The hero's focal phrase ("Bayesian workflow") in the brand's cool-spectrum — a violet → periwinkle →
// aqua gradient clipped to the text, pulled from the same per-mode chip hues the Archive tags use, so
// it reads as a brand accent in both light and dark. The hues drift left-to-right on a slow loop (a
// touch slower than GoldText's shimmer), and the gradient is mirrored so the sweep is seamless. Kept
// distinct from GoldText (reserved for the "gold standard" payoff) so the two hero accents never compete.
export function AccentText({ children }: { children: React.ReactNode }) {
  return (
    <Box
      component="span"
      sx={(theme) => {
        const { violet, periwinkle, aqua } = theme.palette;
        // mirrored stops (…→aqua→periwinkle→violet) so the loop wraps without a colour seam
        const stops = [violet.main, periwinkle.main, aqua.main, periwinkle.main, violet.main].join(", ");
        return {
          backgroundImage: `linear-gradient(100deg, ${stops})`,
          backgroundSize: "200% 100%",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
          WebkitTextFillColor: "transparent",
          animation: "accentShift 12s linear infinite",
          "@keyframes accentShift": {
            "0%": { backgroundPosition: "0% 50%" },
            "100%": { backgroundPosition: "200% 50%" },
          },
          "@media (prefers-reduced-motion: reduce)": { animation: "none" },
        };
      }}
    >
      {children}
    </Box>
  );
}
