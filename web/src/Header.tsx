import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import { AppBar, Box, Container, IconButton, Toolbar } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { useColorMode } from "./useColorMode";

// The brand wordmark (an SVG lockup that already contains the "Bayesify" text), a link to the home
// route. Two ink variants ship in web/public: the dark-ink logo for light mode, the white-ink logo
// for dark mode — swap by the active theme so it always reads against the aurora.
function Wordmark() {
  const { variant } = useColorMode();
  const src = variant === "dark" ? "/bayesify-light.svg" : "/bayesify-dark.svg";
  return (
    <Box
      component={RouterLink}
      to="/"
      sx={{
        display: "flex",
        alignItems: "center",
        textDecoration: "none",
        "&:hover": { opacity: 0.85 },
      }}
    >
      <Box component="img" src={src} alt="Bayesify" sx={{ height: 28, width: "auto", display: "block" }} />
    </Box>
  );
}

// The permanent app header: a single transparent bar rendered once by Layout, consistent across
// every page so the wordmark never moves. Transparent so the global aurora shows through and blends;
// it sits outside the scroll area (Layout), so content never slides under it.
export function Header() {
  const { variant, toggle } = useColorMode();
  return (
    <AppBar
      component="header"
      position="static"
      elevation={0}
      sx={{ background: "transparent", color: "text.primary" }}
    >
      <Container maxWidth={false} sx={{ px: { xs: 2.5, sm: 4, md: 5 } }}>
        <Toolbar disableGutters sx={{ justifyContent: "space-between", py: 2.5, minHeight: { xs: 76, md: 88 } }}>
          <Wordmark />
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <IconButton onClick={toggle} size="small" aria-label="toggle dark mode" sx={{ color: "inherit" }}>
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
