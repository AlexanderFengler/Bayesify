import { Alert, Box, Button, Container, Divider, Link, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { sendContact } from "./api";
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
  { name: "BayesOps", logoDark: "/bayesops-dark.svg", logoLight: "/bayesops-light.svg", url: "https://bayesops.com" },
  {
    name: "Laboratory of Neural Computation and Cognition",
    logoDark: "/lncc-dark.png",
    logoLight: "/lncc-light.png",
    url: "https://www.lnccbrown.com/",
  },
];

// The people who build Bayesify. Add one entry per developer, shown as a simple linked list under
// the org logos. Leave the array empty to hide the section entirely.
//   >>> ADD DEVELOPER NAMES HERE <<<
const DEVELOPERS: { name: string; url: string }[] = [
  { name: "Alexander Fengler", url: "https://alexanderfengler.github.io/about/" },
  { name: "Stefan T. Radev", url: "https://bayesops.com/members/stefan-radev" },
  { name: "Jerry M. Huang", url: "https://bayesops.com/members/jerry-huang" },
];

// A dedicated "About us" page reached from the footer: the org wordmarks that back the project,
// laid out as a responsive row of logos (no boxes), matching the other reference pages' chrome.
export function AboutUs() {
  const { variant } = useColorMode();
  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box
        sx={{
          display: "flex",
          flexDirection: { xs: "column", md: "row" },
          alignItems: "flex-start",
          gap: { xs: 6, md: 8 },
        }}
      >
        {/* Left column: who builds and backs Bayesify (unchanged content). */}
        <Box sx={{ flex: "1 1 0", minWidth: 0, width: "100%" }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: "-0.01em" }}>
              About us
            </Typography>
            <Typography sx={{ mt: 1.5, color: "text.secondary", maxWidth: 760 }}>
              Bayesify is built and supported by the organisations below.
            </Typography>
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

          {DEVELOPERS.length > 0 && (
            <Box sx={{ mt: { xs: 5, md: 7 } }}>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                The team
              </Typography>
              <Box
                component="ul"
                sx={{ listStyle: "none", p: 0, m: 0, mt: 1.5, display: "flex", flexWrap: "wrap", gap: { xs: 1, md: 2 } }}
              >
                {DEVELOPERS.map((dev, i) => (
                  <Typography
                    key={dev.name}
                    component="li"
                    sx={{
                      color: "text.secondary",
                      display: "flex",
                      alignItems: "center",
                      gap: { xs: 1, md: 2 },
                    }}
                  >
                    {/* a white bullet dot separates members — omitted before the first */}
                    {i > 0 && (
                      <Box
                        component="span"
                        sx={{ width: 4, height: 4, borderRadius: "50%", bgcolor: "common.white", flexShrink: 0 }}
                      />
                    )}
                    <Link href={dev.url} target="_blank" rel="noreferrer" underline="hover" color="inherit">
                      {dev.name}
                    </Link>
                  </Typography>
                ))}
              </Box>
            </Box>
          )}
        </Box>

        {/* A divider between the two sides: vertical on the desktop two-column layout, horizontal
            (full-width) once the columns stack on mobile. */}
        <Divider
          orientation="vertical"
          flexItem
          sx={{ display: { xs: "none", md: "block" } }}
        />
        <Divider sx={{ display: { xs: "block", md: "none" }, width: "100%" }} />

        {/* Right column: the contact form. */}
        <Box sx={{ flex: "1 1 0", minWidth: 0, width: "100%", maxWidth: { md: 480 } }}>
          <ContactForm />
        </Box>
      </Box>
    </Container>
  );
}

// A short contact form on the About-us page. Posts to the backend, which relays the message to the
// team by email (via Resend). Client-side required-field checks keep the round-trip cheap; the
// server still validates. On success the form is replaced by a thank-you; errors show inline and
// leave the draft intact so it can be retried.
function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim() && email.trim() && message.trim() && status !== "sending";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setStatus("sending");
    setError(null);
    try {
      await sendContact({ name: name.trim(), email: email.trim(), message: message.trim() });
      setStatus("sent");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Could not send your message.");
    }
  };

  if (status === "sent") {
    return (
      <Box>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Get in touch
        </Typography>
        <Alert severity="success" sx={{ mt: 2 }}>
          Thanks — your message is on its way. We&rsquo;ll be in touch.
        </Alert>
      </Box>
    );
  }

  return (
    <Box component="form" onSubmit={submit} noValidate>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>
        Get in touch
      </Typography>
      <Typography sx={{ mt: 1, mb: 2.5, color: "text.secondary" }}>
        Questions, feedback, or a collaboration in mind? Send us a note.
      </Typography>
      <Stack spacing={2}>
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          fullWidth
          size="small"
          disabled={status === "sending"}
        />
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          fullWidth
          size="small"
          disabled={status === "sending"}
        />
        <TextField
          label="Message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          required
          fullWidth
          multiline
          minRows={5}
          disabled={status === "sending"}
        />
        {error && <Alert severity="error">{error}</Alert>}
        <Box>
          <Button type="submit" variant="contained" disableElevation disabled={!canSubmit}>
            {status === "sending" ? "Sending…" : "Send message"}
          </Button>
        </Box>
      </Stack>
    </Box>
  );
}
