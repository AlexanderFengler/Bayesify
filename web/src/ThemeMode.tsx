import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { createContext, useContext, useMemo, useState } from "react";
import { type AuroraVariant, makeTheme } from "./theme";

interface ColorMode {
  variant: AuroraVariant;
  toggle: () => void;
}
const ColorModeContext = createContext<ColorMode>({ variant: "teal", toggle: () => {} });
export const useColorMode = () => useContext(ColorModeContext);

const KEY = "bayesify.aurora"; // persisted aurora variant

// Holds the active aurora variant (teal default / indigo dark), builds the matching MUI theme, and
// exposes a toggle. Sits above the Router so the whole app (including Aurora) re-themes on switch.
export function AppThemeProvider({ children }: { children: React.ReactNode }) {
  const [variant, setVariant] = useState<AuroraVariant>(
    () => (localStorage.getItem(KEY) as AuroraVariant | null) ?? "teal",
  );
  const theme = useMemo(() => makeTheme(variant), [variant]);
  const ctx = useMemo<ColorMode>(
    () => ({
      variant,
      toggle: () =>
        setVariant((v) => {
          const next: AuroraVariant = v === "teal" ? "indigo" : "teal";
          localStorage.setItem(KEY, next);
          return next;
        }),
    }),
    [variant],
  );
  return (
    <ColorModeContext.Provider value={ctx}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
