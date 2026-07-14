import { Box, Container, Link, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

// Current app version, surfaced as the footer's alpha-stage marker. Keep in step with package.json.
const APP_VERSION = "0.1.1";

// The permanent app footer: a single transparent bar rendered once by Layout (like the header), so
// the dynamic aurora shows through and blends with it. A thin horizontal divider sits on top. It
// carries the global nav: how-it-works, rubrics, archive, and the about-us reference.
export function Footer() {
  const navigate = useNavigate();
  return (
    <Box component="footer" sx={{ color: "text.secondary", borderTop: 1, borderColor: "divider" }}>
      <Container maxWidth={false}>
        <Box
          sx={{
            display: "flex",
            flexDirection: { xs: "column", sm: "row" },
            gap: 2,
            justifyContent: { xs: "flex-start", sm: "space-between" },
            alignItems: { xs: "flex-start", sm: "center" },
            py: 3,
          }}
        >
          <Typography variant="body2" sx={{ color: "inherit", fontSize: "0.875rem" }}>
            Beta version - {APP_VERSION}
          </Typography>
          <Box sx={{ display: "flex", gap: 3 }}>
            {/* How-it-works and Rubrics are sections of the main page now (still addressable at
                /#how-it-works and /#rubrics) — the footer only carries the standalone pages */}
            <FooterLink onClick={() => navigate("/")}>Home</FooterLink>
            <FooterLink onClick={() => navigate("/archive")}>Archive</FooterLink>
            <FooterLink onClick={() => navigate("/about")}>About us</FooterLink>
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
