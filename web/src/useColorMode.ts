import { createContext, useContext } from "react";
import type { AuroraVariant } from "./theme";

// The active aurora variant (dark default / light) + a toggle. Kept in its own module (not in
// ThemeMode.tsx) so the provider file exports only a component — react-refresh's
// only-export-components rule flags a file that mixes a component with a hook/context export.
export interface ColorMode {
  variant: AuroraVariant;
  toggle: () => void;
}

export const ColorModeContext = createContext<ColorMode>({ variant: "dark", toggle: () => {} });

export const useColorMode = () => useContext(ColorModeContext);
