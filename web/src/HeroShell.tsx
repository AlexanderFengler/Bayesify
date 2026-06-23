import { Box, Container } from "@mui/material";

// The immersive aurora band shared by the full-bleed screens (cover, landing, analyzing): a bold
// accent gradient that fills the routed content area, with the page's content centered inside and an
// optional footer slot below. The header is NOT here — it lives in <Header>, rendered permanently by
// Layout so it doesn't fade during page transitions. This shell fills the area beneath that header.
export function HeroShell({ children, footer }: { children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
      <Box
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          color: "common.white",
          // Dynamic flowy "aurora" between the two brand teals: several over-sized radial colour
          // pools layered over a base gradient, each drifting along its own path so the colours
          // merge and separate organically. One master keyframe moves every layer's position (each
          // a different size/start, so they never move in lockstep). Falls back to a flat fill and
          // stops animating for users who prefer reduced motion.
          backgroundColor: "#103a52",
          backgroundImage: [
            "radial-gradient(38% 46% at 22% 30%, rgba(0,140,170,0.60), transparent 62%)",
            "radial-gradient(42% 52% at 80% 32%, rgba(0,115,150,0.62), transparent 66%)",
            "radial-gradient(46% 56% at 62% 80%, rgba(36,170,200,0.42), transparent 60%)",
            "radial-gradient(50% 60% at 14% 82%, rgba(21,67,95,0.70), transparent 66%)",
            "linear-gradient(130deg, #15435f 0%, #007396 100%)",
          ].join(", "),
          backgroundSize: "180% 180%, 200% 200%, 220% 220%, 200% 200%, 160% 160%",
          animation: "heroFlow 28s ease-in-out infinite",
          "@keyframes heroFlow": {
            "0%": {
              backgroundPosition: "0% 0%, 100% 50%, 50% 100%, 0% 100%, 0% 50%",
            },
            "50%": {
              backgroundPosition: "100% 100%, 0% 60%, 0% 0%, 100% 0%, 100% 50%",
            },
            "100%": {
              backgroundPosition: "0% 0%, 100% 50%, 50% 100%, 0% 100%, 0% 50%",
            },
          },
          "@media (prefers-reduced-motion: reduce)": { animation: "none" },
        }}
      >
        {/* page content, centered in the space below the (permanent) header */}
        <Box sx={{ flex: 1, display: "flex", alignItems: "center" }}>
          <Container maxWidth="lg" sx={{ py: { xs: 4, md: 6 } }}>
            {children}
          </Container>
        </Box>
      </Box>
      {footer}
    </Box>
  );
}
