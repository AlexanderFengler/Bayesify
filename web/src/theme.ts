import { createTheme, type Theme } from "@mui/material/styles";

// The app runs as an immersive, light-on-dark UI: every screen floats over the animated aurora, with
// frosted-glass panels instead of opaque light cards. Two aurora variants ship — the default teal and
// a "dark mode" purple→indigo — chosen at runtime. Both keep the signifier hues (success/warning/
// error/info) identical so status colours never shift meaning.
export type AuroraVariant = "teal" | "indigo";

const typeface = {
  font: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
  heading: '"Rubik", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  mono: '"SF Mono", ui-monospace, "Roboto Mono", Menlo, Consolas, monospace',
};

// Signifier colours — shared across every variant/mode, never themed.
const signifier = {
  green: "#2f9e5e",
  greenSoft: "#e9f6ee",
  amber: "#c9810b",
  amberSoft: "#fbf1dc",
  red: "#d1483b",
  redSoft: "#fae9e7",
  blue: "#2d74c4",
  blueSoft: "#e8f1fb",
};

// Per-variant: the accent colour, a soft translucent accent for fills/hovers, the frosted-glass panel
// tint, and the aurora itself (a base fill + layered radial pools that drift over a base gradient).
const VARIANTS: Record<
  AuroraVariant,
  { primary: string; primarySoft: string; contrast: string; glass: string; aurora: { base: string; image: string; size: string } }
> = {
  // Default — brand teals, now with a bright #47b5ff pool woven in; gradients blend the three.
  teal: {
    primary: "#4cc2ff",
    primarySoft: "rgba(76,194,255,0.18)",
    contrast: "#06202e",
    glass: "rgba(9,30,45,0.55)",
    aurora: {
      base: "#0c2f44",
      image: [
        "radial-gradient(40% 48% at 20% 28%, rgba(0,115,150,0.60), transparent 62%)", // #007396
        "radial-gradient(44% 54% at 82% 30%, rgba(71,181,255,0.42), transparent 66%)", // #47b5ff
        "radial-gradient(46% 56% at 60% 82%, rgba(21,67,95,0.65), transparent 60%)", // #15435f
        "radial-gradient(52% 62% at 12% 84%, rgba(71,181,255,0.28), transparent 66%)", // #47b5ff
        "linear-gradient(130deg, #15435f 0%, #007396 55%, #2f93d6 100%)",
      ].join(", "),
      size: "180% 180%, 200% 200%, 220% 220%, 210% 210%, 160% 160%",
    },
  },
  // Dark mode — dark purple → indigo, cool complementary scheme.
  indigo: {
    primary: "#a78bfa",
    primarySoft: "rgba(167,139,250,0.20)",
    contrast: "#1a1438",
    glass: "rgba(22,16,44,0.58)",
    aurora: {
      base: "#15122e",
      image: [
        "radial-gradient(40% 48% at 20% 28%, rgba(79,70,229,0.50), transparent 62%)", // #4f46e5
        "radial-gradient(44% 54% at 82% 30%, rgba(124,58,237,0.45), transparent 66%)", // #7c3aed
        "radial-gradient(46% 56% at 60% 82%, rgba(49,46,129,0.65), transparent 60%)", // #312e81
        "radial-gradient(52% 62% at 12% 84%, rgba(129,140,248,0.30), transparent 66%)", // #818cf8
        "linear-gradient(130deg, #241a52 0%, #3b2f8f 55%, #4f46e5 100%)",
      ].join(", "),
      size: "180% 180%, 200% 200%, 220% 220%, 210% 210%, 160% 160%",
    },
  },
};

function buildTokens(variant: AuroraVariant) {
  const v = VARIANTS[variant];
  return {
    radius: 12,
    ...typeface,
    ...signifier,
    variant,
    primary: v.primary,
    glass: v.glass,
    lineStrong: "rgba(255,255,255,0.22)",
    aurora: v.aurora,
  };
}
type Tokens = ReturnType<typeof buildTokens>;

export function makeTheme(variant: AuroraVariant): Theme {
  const v = VARIANTS[variant];
  const tokens = buildTokens(variant);
  const heading = { fontFamily: typeface.heading } as const;

  return createTheme({
    palette: {
      mode: "dark",
      primary: { main: v.primary, light: v.primarySoft, contrastText: v.contrast },
      success: { main: signifier.green, light: signifier.greenSoft },
      warning: { main: signifier.amber, light: signifier.amberSoft },
      error: { main: signifier.red, light: signifier.redSoft },
      info: { main: signifier.blue, light: signifier.blueSoft },
      text: {
        primary: "rgba(255,255,255,0.92)",
        secondary: "rgba(255,255,255,0.66)",
        disabled: "rgba(255,255,255,0.40)",
      },
      // default is transparent so content floats on the aurora; paper is the frosted glass tint.
      background: { default: "transparent", paper: v.glass },
      divider: "rgba(255,255,255,0.14)",
    },
    shape: { borderRadius: tokens.radius },
    typography: {
      fontFamily: typeface.font,
      fontSize: 15,
      button: { textTransform: "none", fontWeight: 600 },
      h1: heading,
      h2: heading,
      h3: heading,
      h4: heading,
      h5: heading,
      h6: heading,
      overline: heading,
    },
    components: {
      // The base fill behind the fixed aurora layer (prevents white overscroll edges).
      MuiCssBaseline: { styleOverrides: { body: { backgroundColor: v.aurora.base } } },
      // Every Paper becomes a frosted-glass panel — translucent, blurred, hairline-bordered — so the
      // aurora reads through it. This is what makes the boxes immersive rather than light surfaces.
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: "none",
            backgroundColor: v.glass,
            backdropFilter: "blur(14px)",
            border: "1px solid rgba(255,255,255,0.12)",
          },
        },
      },
      // AppBar also extends Paper — keep the header truly transparent (no glass, no border, no blur).
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: "transparent",
            backgroundImage: "none",
            border: "none",
            backdropFilter: "none",
            boxShadow: "none",
          },
        },
      },
    },
    tokens,
  });
}

// Make `theme.tokens` type-safe in sx callbacks and styled().
declare module "@mui/material/styles" {
  interface Theme {
    tokens: Tokens;
  }
  interface ThemeOptions {
    tokens?: Tokens;
  }
}
