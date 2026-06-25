import { Box, Button, Container, Link, Typography } from "@mui/material";
import { useColorMode } from "./ThemeMode";

// The organisations behind Bayesify. Add an entry per org — each ships a dark-ink and a white-ink
// wordmark in web/public so it reads against the aurora in either colour mode. `url` is optional.
type Org = {
  name: string;
  logoDark: string; // dark-ink wordmark — shown in light mode
  logoLight: string; // white-ink wordmark — shown in dark mode
  url?: string;
};

const ORGS: Org[] = [
  { name: "VeriBayes", logoDark: "/org-logo-dark.svg", logoLight: "/org-logo-light.svg" },
];

// A dedicated "Supported by" page reached from the footer: the org wordmarks that back the project,
// laid out as a responsive row of logos (no boxes), matching the other reference pages' chrome.
export function SupportedBy({ onExit }: { onExit: () => void }) {
  const { variant } = useColorMode();
  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
            Supported by
          </Typography>
          <Typography sx={{ mt: 1.5, color: "text.secondary", maxWidth: 760 }}>
            Bayesify is built and supported by the organisations below.
          </Typography>
        </Box>
        <Button variant="outlined" onClick={onExit} sx={{ flexShrink: 0 }}>
          Back
        </Button>
      </Box>

      <Box
        sx={{
          mt: { xs: 4, md: 6 },
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: { xs: 4, md: 6 },
        }}
      >
        {ORGS.map((org) => {
          // dark-ink wordmark for light mode, white-ink for dark mode — so it reads against the aurora
          const src = variant === "dark" ? org.logoLight : org.logoDark;
          const logo = (
            <Box
              component="img"
              src={src}
              alt={org.name}
              sx={{ height: { xs: 40, md: 52 }, width: "auto", display: "block" }}
            />
          );
          return org.url ? (
            <Link key={org.name} href={org.url} target="_blank" rel="noreferrer" sx={{ display: "block" }}>
              {logo}
            </Link>
          ) : (
            <Box key={org.name}>{logo}</Box>
          );
        })}
      </Box>
    </Container>
  );
}
