import LockIcon from "@mui/icons-material/Lock";
import PublicIcon from "@mui/icons-material/Public";
import { AppBar, Chip, Container, Toolbar, Typography } from "@mui/material";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { useApp } from "./AppContext";

// The brand wordmark, a link to the home route.
function Wordmark() {
  return (
    <Typography
      variant="h6"
      component={RouterLink}
      to="/"
      sx={{
        fontWeight: 700,
        letterSpacing: "-0.01em",
        color: "inherit",
        textDecoration: "none",
        "&:hover": { opacity: 0.85 },
      }}
    >
      Bayesify
    </Typography>
  );
}

// Always-visible reminder of the outbound data path for the current mode (PRIVACY.md F3).
function ModeChip({ mode }: { mode: "full" | "local" }) {
  const sx = {
    bgcolor: "rgba(255,255,255,0.16)",
    color: "common.white",
    "& .MuiChip-icon": { color: "inherit" },
  } as const;
  return mode === "local" ? (
    <Chip icon={<LockIcon sx={{ fontSize: 16 }} />} label="Local-only · nothing leaves this machine" size="small" sx={sx} />
  ) : (
    <Chip icon={<PublicIcon sx={{ fontSize: 16 }} />} label="Full · text sent to Anthropic" size="small" sx={sx} />
  );
}

// The permanent app header: a single sticky top bar rendered once by Layout, so it stays put while
// the routed content cross-fades beneath it. Route-aware: the cover (`/`) spans the full viewport and
// shows no mode chip (it starts no analysis); every other screen is lg-width with the mode reminder.
export function Header() {
  const { pathname } = useLocation();
  const { mode } = useApp();
  const isCover = pathname === "/";
  return (
    <AppBar
      component="header"
      position="sticky"
      elevation={0}
      sx={{ color: "common.white", backgroundImage: "linear-gradient(130deg, #15435f 0%, #007396 100%)" }}
    >
      <Container maxWidth={isCover ? false : "lg"}>
        <Toolbar disableGutters sx={{ justifyContent: "space-between" }}>
          <Wordmark />
          {!isCover && <ModeChip mode={mode} />}
        </Toolbar>
      </Container>
    </AppBar>
  );
}
