// Minimal, provider-agnostic frontend error monitoring — the whole "infrastructure" is one choke
// point, `reportError`, that every error source funnels through:
//   - React render crashes  → ErrorBoundary.componentDidCatch calls it
//   - uncaught runtime errors + unhandled promise rejections → the global handlers below call it
// It normalizes each error into one shape and hands it to `send`. Today `send` logs to the console
// (the only zero-infra, frontend-only sink); shipping errors off the device later is a one-line
// change in `send` alone — no call site moves.

export type ErrorSource = "react" | "window" | "unhandledrejection";

export interface ErrorReport {
  message: string;
  stack?: string;
  componentStack?: string;
  source: ErrorSource;
  url: string;
  userAgent: string;
  timestamp: string;
}

// The sink. Replace this body to send errors somewhere real — e.g.
//   navigator.sendBeacon("/api/client-errors", JSON.stringify(report));
// or Sentry.captureException(...) — without touching any caller.
function send(report: ErrorReport): void {
  console.error(`[telemetry:${report.source}] ${report.message}`, report);
}

// The single entry point. Accepts anything thrown (Error or not) and never throws itself — a broken
// reporter must not become a second error.
export function reportError(error: unknown, context?: { source?: ErrorSource; componentStack?: string | null }): void {
  try {
    const err = error instanceof Error ? error : new Error(typeof error === "string" ? error : JSON.stringify(error));
    send({
      message: err.message,
      stack: err.stack,
      componentStack: context?.componentStack ?? undefined,
      source: context?.source ?? "react",
      url: window.location.href,
      userAgent: navigator.userAgent,
      timestamp: new Date().toISOString(),
    });
  } catch {
    // Swallow: telemetry must be best-effort. A failure here (e.g. a circular value in JSON.stringify)
    // is never worth surfacing to the user or masking the original error.
  }
}

// Catches errors outside React's render path — uncaught exceptions in event handlers / async code and
// unhandled promise rejections — which an ErrorBoundary alone never sees. Call once from main.tsx.
// Idempotent so React StrictMode's double-invoke (dev) can't double-register the listeners.
let installed = false;
export function installGlobalErrorHandlers(): void {
  if (installed) return;
  installed = true;
  window.addEventListener("error", (e) => reportError(e.error ?? e.message, { source: "window" }));
  window.addEventListener("unhandledrejection", (e) => reportError(e.reason, { source: "unhandledrejection" }));
}
