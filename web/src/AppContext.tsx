import { createContext, useContext } from "react";
import type { RubricSummary } from "./api";
import type { PaperState } from "./types";

// The app-wide state that can't live in the URL: the analysis mode, the upload draft, the in-flight
// streaming lifecycle, and the privacy modal. Provided by Layout (which sits inside the Router so it
// can navigate) and consumed by the route pages via the useApp() hook below.
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
  stageState: Record<string, "running" | "done">;
  paper: PaperState | null;
  setPaper: (p: PaperState | null) => void;
  error: string | null;

  // actions (each navigates as needed)
  start: (intent?: "analyze" | "rate") => void;
  rerunPaper: (paperId: string) => void;
  reset: () => void;
  openPrivacy: () => void;
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within <Layout>");
  return ctx;
}
