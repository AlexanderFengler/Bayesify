import { Box, Container, Divider, Link, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useApp } from "./AppContext";
import { useColorMode } from "./ThemeMode";

// The permanent app footer: a single transparent bar rendered once by Layout (like the header), so
// the dynamic aurora shows through and blends with it. A thin horizontal divider sits on top. It
// carries the global nav: how-it-works, privacy, calibration, and the rubrics reference.
export function Footer() {
  const navigate = useNavigate();
  const { openPrivacy } = useApp();
  const { variant } = useColorMode();
  // dark-ink org wordmark for light mode, white-ink for dark mode — so it reads against the aurora
  const orgLogo = variant === "dark" ? "/org-logo-light.svg" : "/org-logo-dark.svg";
  return (
    <Box
      component="footer"
      sx={{ color: "text.secondary", borderTop: 1, borderColor: "divider" }}
    >
      <Container maxWidth={false}>
        <Box
          sx={{
            display: "flex",
            flexDirection: { xs: "column", sm: "row" },
            gap: 2,
            justifyContent: "space-between",
            alignItems: { xs: "flex-start", sm: "center" },
            py: 3,
          }}
        >
          {/* attribution: "Product of [org logo]" · a thin vertical rule · the formative-report note */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, maxWidth: 720 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Product of
              </Typography>
              <Box
                component="img"
                src={orgLogo}
                alt="VeriBayes"
                sx={{ height: 22, width: "auto", display: "block" }}
              />
            </Box>
            <Divider orientation="vertical" flexItem sx={{ my: 0.25 }} />
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Formative report, not a verdict — Bayesify reports per-step practice, not a pass/fail.
            </Typography>
          </Box>
          <Box sx={{ display: "flex", gap: 3 }}>
            <FooterLink onClick={() => navigate("/guide")}>How it works</FooterLink>
            <FooterLink onClick={() => navigate("/rubrics")}>Rubrics</FooterLink>
            <FooterLink onClick={openPrivacy}>Privacy</FooterLink>
            <FooterLink onClick={() => navigate("/calibration")}>Calibration</FooterLink>
          </Box>
        </Box>
      </Container>
    </Box>
  );
}

function FooterLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <Link
      component="button"
      type="button"
      underline="hover"
      onClick={onClick}
      sx={{ color: "inherit", fontSize: "0.875rem", "&:hover": { color: "text.primary" } }}
    >
      {children}
    </Link>
  );
}
