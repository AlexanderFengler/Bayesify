import LockIcon from "@mui/icons-material/Lock";
import PublicIcon from "@mui/icons-material/Public";
import { AppBar, Box, Chip, Container, Toolbar, Typography } from "@mui/material";

// The immersive page shell shared by every full-bleed screen (landing, analyzing, …): a bold accent
// gradient band that fills the viewport, with the brand wordmark + the always-on mode indicator at
// the top and the page's content centered beneath. An optional footer slot sits below the hero.
// Centralizing it keeps the migrated screens visually identical and DRY.
export function HeroShell({
  mode,
  children,
  footer,
}: {
  mode: "full" | "local";
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <Box sx={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
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
        {/* the title + mode live in a transparent header bar pinned to the top of the hero */}
        <AppBar
          component="header"
          position="static"
          elevation={0}
          sx={{ background: "transparent", color: "common.white" }}
        >
          <Container maxWidth="lg">
            <Toolbar disableGutters sx={{ justifyContent: "space-between" }}>
              <Typography variant="h6" component="div" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
                Bayesify
              </Typography>
              <ModeChip mode={mode} />
            </Toolbar>
          </Container>
        </AppBar>
        {/* page content, centered in the space below the header */}
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

// The sticky top bar for content pages (report, inventory): brand + mode on a static teal gradient,
// since those pages sit on a light surface rather than the animated hero.
export function TopBar({ mode }: { mode: "full" | "local" }) {
  return (
    <AppBar
      component="header"
      position="sticky"
      elevation={0}
      sx={{ color: "common.white", backgroundImage: "linear-gradient(130deg, #15435f 0%, #007396 100%)" }}
    >
      <Container maxWidth="lg">
        <Toolbar disableGutters sx={{ justifyContent: "space-between" }}>
          <Typography variant="h6" component="div" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
            Bayesify
          </Typography>
          <ModeChip mode={mode} />
        </Toolbar>
      </Container>
    </AppBar>
  );
}

// Always-visible reminder of the outbound data path for the current mode (PRIVACY.md F3), styled to
// sit on the bold hero.
export function ModeChip({ mode }: { mode: "full" | "local" }) {
  const sx = {
    bgcolor: "rgba(255,255,255,0.16)",
    color: "common.white",
    "& .MuiChip-icon": { color: "inherit" },
  } as const;
  return mode === "local" ? (
    <Chip
      icon={<LockIcon sx={{ fontSize: 16 }} />}
      label="Local-only · nothing leaves this machine"
      size="small"
      sx={sx}
    />
  ) : (
    <Chip
      icon={<PublicIcon sx={{ fontSize: 16 }} />}
      label="Full · text sent to Anthropic"
      size="small"
      sx={sx}
    />
  );
}
