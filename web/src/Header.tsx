import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import LockIcon from "@mui/icons-material/Lock";
import PublicIcon from "@mui/icons-material/Public";
import { AppBar, Box, Chip, Container, IconButton, Toolbar, Typography } from "@mui/material";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { useApp } from "./AppContext";
import { useColorMode } from "./ThemeMode";

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
    bgcolor: "action.selected",
    color: "text.primary",
    "& .MuiChip-icon": { color: "inherit" },
  } as const;
  return mode === "local" ? (
    <Chip icon={<LockIcon sx={{ fontSize: 16 }} />} label="Local-only · nothing leaves this machine" size="small" sx={sx} />
  ) : (
    <Chip icon={<PublicIcon sx={{ fontSize: 16 }} />} label="Full · text sent to Anthropic" size="small" sx={sx} />
  );
}

// The permanent app header: a single transparent bar rendered once by Layout, consistent across
// every page so the wordmark never moves. Transparent so the global aurora shows through and blends;
// it sits outside the scroll area (Layout), so content never slides under it. The only per-page
// difference is the cover (`/`), which shows no mode chip (it starts no analysis).
export function Header() {
  const { pathname } = useLocation();
  const { mode } = useApp();
  const { variant, toggle } = useColorMode();
  const isCover = pathname === "/";
  return (
    <AppBar
      component="header"
      position="static"
      elevation={0}
      sx={{ background: "transparent", color: "text.primary" }}
    >
      <Container maxWidth={false}>
        <Toolbar disableGutters sx={{ justifyContent: "space-between" }}>
          <Wordmark />
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            {!isCover && <ModeChip mode={mode} />}
            <IconButton
              onClick={toggle}
              size="small"
              aria-label="toggle dark mode"
              sx={{ color: "inherit" }}
            >
              {variant === "light" ? (
                <DarkModeOutlinedIcon fontSize="small" />
              ) : (
                <LightModeOutlinedIcon fontSize="small" />
              )}
            </IconButton>
          </Box>
        </Toolbar>
      </Container>
    </AppBar>
  );
}
