import { Box, Container, Link } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useApp } from "./AppContext";

// The permanent app footer: a single transparent bar rendered once by Layout (like the header), so
// the dynamic aurora shows through and blends with it. A thin horizontal divider sits on top. It
// carries the global nav: how-it-works, rubrics, privacy, and the supporters reference.
export function Footer() {
  const navigate = useNavigate();
  const { openPrivacy } = useApp();
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
            justifyContent: { xs: "flex-start", sm: "flex-end" },
            alignItems: { xs: "flex-start", sm: "center" },
            py: 3,
          }}
        >
          <Box sx={{ display: "flex", gap: 3 }}>
            <FooterLink onClick={() => navigate("/guide")}>How it works</FooterLink>
            <FooterLink onClick={() => navigate("/rubrics")}>Rubrics</FooterLink>
            <FooterLink onClick={openPrivacy}>Privacy</FooterLink>
            <FooterLink onClick={() => navigate("/supported")}>Supported by</FooterLink>
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
