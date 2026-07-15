import { createContext, useContext } from "react";
import type { RubricSummary } from "./api";
import type { PaperState } from "./types";

// The app-wide state that can't live in the URL: the analysis mode, the upload draft, and the
// in-flight streaming lifecycle. Provided by Layout (which sits inside the Router so it can
// navigate) and consumed by the route pages via the useApp() hook below.
export interface AppState {
  mode: "full" | "local";
  setMode: (m: "full" | "local") => void;
  profile: string;
  setProfile: (p: string) => void;
  rubrics: RubricSummary[];

  // the upload draft (the landing form)
  identifier: string;
  setIdentifier: (s: string) => void;
  file: File | null;
  setFile: (f: File | null) => void;
  dragging: boolean;
  setDragging: (b: boolean) => void;
  fileInput: React.RefObject<HTMLInputElement>;

  // the in-flight run (drives the /processing page)
  running: boolean;
  archiveHit: string | null; // completed paper id shown briefly before its report redirect
  ratingPending: string | null; // paper id whose rating-feeding run is still in flight (or null)
  stageState: Record<string, "running" | "done" | "failed">;
  paper: PaperState | null;
  setPaper: (p: PaperState | null) => void;
  error: string | null;
  // A fetch-stage failure (couldn't acquire the PDF for a pasted identifier). Surfaced back on the
  // landing form so the user can try another identifier or upload the PDF, rather than a dead-end page.
  fetchError: string | null;

  // actions (each navigates as needed)
  start: (intent?: "analyze" | "rate") => void;
  rerunPaper: (paperId: string) => void;
  reset: () => void;
  exitToMain: () => void; // return to the last main/report page (reference-page Back)
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within <Layout>");
  return ctx;
}
