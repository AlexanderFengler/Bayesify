import { Alert, AlertTitle, Button, Container, Link } from "@mui/material";
import { Component, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";
import { reportError } from "./telemetry";

// The app-wide render-error net. Without a boundary, any throw during render unmounts the entire
// tree — a blank white page with no way out. This catches the throw and fills the content area with
// the same error panel the routed pages use. Recovery is a full reload (fresh state) rather than a
// state reset: a render throw means some state is already inconsistent, so retrying in place would
// usually just throw again. Class component because error boundaries have no hook equivalent.
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Funnel render crashes through the shared telemetry seam (which keeps the component stack).
    reportError(error, { source: "react", componentStack: info.componentStack });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 } }}>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => window.location.reload()}>
              Reload
            </Button>
          }
        >
          <AlertTitle>Something went wrong</AlertTitle>
          The page hit an unexpected error. Reloading usually fixes it; if it keeps happening, please let us know via
          the{" "}
          <Link
            component={RouterLink}
            to="/about"
            underline="none"
            color="inherit"
            sx={{ fontWeight: 600 }}
            onClick={() => this.setState({ error: null })}
          >
            contact form
          </Link>
          .
        </Alert>
      </Container>
    );
  }
}
