import { createTheme } from "@mui/material/styles";

// The MUI theme is a faithful port of the design tokens in styles.css (:root). Keeping the two in
// sync means MUI components render on-brand from the first drop-in, and as screens migrate off the
// hand-rolled CSS the visual language doesn't shift. When a token changes, change it in both places
// (or, eventually, drive styles.css from these values) — these are the source of truth for MUI.
const tokens = {
  bg: "#f6f7f9",
  surface: "#ffffff",
  ink: "#1b2230",
  inkSoft: "#5b6678",
  inkFaint: "#8a93a3",
  line: "#e6e9ef",
  lineStrong: "#d3d9e2",
  accent: "#3b5bdb",
  accentSoft: "#edf0fd",
  green: "#2f9e5e",
  greenSoft: "#e9f6ee",
  amber: "#c9810b",
  amberSoft: "#fbf1dc",
  red: "#d1483b",
  redSoft: "#fae9e7",
  blue: "#2d74c4",
  blueSoft: "#e8f1fb",
  radius: 12,
  font: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  mono: '"SF Mono", ui-monospace, "Roboto Mono", Menlo, Consolas, monospace',
} as const;

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: tokens.accent, light: tokens.accentSoft, contrastText: "#ffffff" },
    success: { main: tokens.green, light: tokens.greenSoft },
    warning: { main: tokens.amber, light: tokens.amberSoft },
    error: { main: tokens.red, light: tokens.redSoft },
    info: { main: tokens.blue, light: tokens.blueSoft },
    text: { primary: tokens.ink, secondary: tokens.inkSoft, disabled: tokens.inkFaint },
    background: { default: tokens.bg, paper: tokens.surface },
    divider: tokens.line,
  },
  shape: { borderRadius: tokens.radius },
  typography: {
    fontFamily: tokens.font,
    fontSize: 15, // styles.css body is 15px; MUI's default html is 16px → keep the existing scale
    button: { textTransform: "none", fontWeight: 600 }, // the current buttons aren't uppercased
  },
  // Expose the extra tokens that don't map onto a standard MUI slot, for use via theme access in sx.
  // (Read as `theme.tokens.lineStrong`, etc. — see the module augmentation below.)
  tokens,
});

// Make `theme.tokens` type-safe in sx callbacks and styled().
declare module "@mui/material/styles" {
  interface Theme {
    tokens: typeof tokens;
  }
  interface ThemeOptions {
    tokens?: typeof tokens;
  }
}
