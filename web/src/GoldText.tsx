import { Box } from "@mui/material";

// "gold standard" in living gold: a metallic gradient clipped to the text, shimmering a touch faster
// than the aurora behind it (~8s vs 28s) so it reads as a focal accent. Shared by the cover hero and
// the rubrics page so the animation stays identical wherever the phrase appears.
export function GoldText({ children }: { children: React.ReactNode }) {
  return (
    <Box
      component="span"
      sx={{
        backgroundImage: "linear-gradient(90deg, #9a6a14, #d9a832, #ffce5a, #d9a832, #9a6a14)",
        backgroundSize: "200% 100%",
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        color: "transparent",
        WebkitTextFillColor: "transparent",
        animation: "goldShift 8s linear infinite",
        "@keyframes goldShift": {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
        "@media (prefers-reduced-motion: reduce)": { animation: "none" },
      }}
    >
      {children}
    </Box>
  );
}
