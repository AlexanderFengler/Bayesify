import { createTheme, type PaletteMode, type Theme } from "@mui/material/styles";

// The app floats every screen over an animated aurora, with frosted-glass panels. Two real modes
// ship: a LIGHT mode (a soft gray aurora, dark purple text, light glass) and a DARK mode (a deep
// purple aurora, light text, dark glass). Each mode carries its own signifier hues (success/warning/
// error/info) — the dark mode's are brighter, for contrast on the dark aurora.
export type AuroraVariant = "light" | "dark";

const typeface = {
  font: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
  heading: '"Rubik", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  mono: '"SF Mono", ui-monospace, "Roboto Mono", Menlo, Consolas, monospace',
};

type Signifier = {
  green: string;
  greenSoft: string;
  amber: string;
  amberSoft: string;
  red: string;
  redSoft: string;
  blue: string;
  blueSoft: string;
};

// Light mode — the original mid-tone signifiers on light pastel fills.
const LIGHT_SIGNIFIER: Signifier = {
  green: "#2f9e5e",
  greenSoft: "#e9f6ee",
  amber: "#c9810b",
  amberSoft: "#fbf1dc",
  red: "#d1483b",
  redSoft: "#fae9e7",
  blue: "#2d74c4",
  blueSoft: "#e8f1fb",
};

// Dark mode — brighter signifiers (better contrast on the dark purple) over translucent tints. The
// hues are chosen to read clearly *against* the purple aurora and apart from each other: a vivid
// emerald (not a muted sage), a warm amber (not a pale yellow), and a true red pulled away from the
// pink/magenta family so "missing" never blends into the purple background.
const DARK_SIGNIFIER: Signifier = {
  green: "#4ade80",
  greenSoft: "rgba(74,222,128,0.20)",
  amber: "#fbbf24",
  amberSoft: "rgba(251,191,36,0.20)",
  red: "#ff6b6b",
  redSoft: "rgba(255,107,107,0.20)",
  blue: "#60a5fa",
  blueSoft: "rgba(96,165,250,0.18)",
};

interface Variant {
  mode: PaletteMode;
  primary: string;
  primarySoft: string;
  contrast: string;
  glass: string;
  glassBorder: string;
  lineStrong: string;
  text: { primary: string; secondary: string; disabled: string };
  divider: string;
  signifier: Signifier;
  // The categorical-tag palette, in two tiers, both kept clear of the signifier hues so a tag is never
  // mistaken for a status color. Vivid tier — a stepped cool-spectrum (periwinkle → aqua → violet →
  // magenta) for what a paper IS (type / discipline / methods / software). Muted tier — desaturated
  // cool tones (slate / steel) for how it was GRADED (rubric / weighting). Each is a mid-tone in light
  // mode (white text) and a brighter tone in dark mode (dark text), matching the signifier build.
  chip: {
    periwinkle: { main: string; soft: string };
    aqua: { main: string; soft: string };
    violet: { main: string; soft: string };
    magenta: { main: string; soft: string };
    slate: { main: string; soft: string };
    steel: { main: string; soft: string };
  };
  aurora: { base: string; image: string; size: string };
}

const SIZE = "180% 180%, 200% 200%, 220% 220%, 210% 210%, 160% 160%";

const VARIANTS: Record<AuroraVariant, Variant> = {
  // Light — a soft gray aurora between rgb(217,217,217) and rgb(240,240,240); purple ink, light glass.
  light: {
    mode: "light",
    primary: "#6d28d9",
    primarySoft: "rgba(109,40,217,0.10)",
    contrast: "#ffffff",
    glass: "rgba(255,255,255,0.62)",
    glassBorder: "rgba(48,16,78,0.12)",
    lineStrong: "rgba(48,16,78,0.24)",
    text: { primary: "#30104e", secondary: "#5b5470", disabled: "#8e88a0" },
    divider: "rgba(48,16,78,0.14)",
    signifier: LIGHT_SIGNIFIER,
    chip: {
      periwinkle: { main: "#6969ff", soft: "#eef0ff" },
      aqua: { main: "#0a90a8", soft: "#e0f4f7" },
      violet: { main: "#9b30d4", soft: "#f5e6fb" },
      magenta: { main: "#cf1d8f", soft: "#fce4f2" },
      slate: { main: "#5f6a94", soft: "#ecedf4" },
      steel: { main: "#4c7f8b", soft: "#e6f1f2" },
    },
    aurora: {
      base: "#e8e8e8",
      image: [
        "radial-gradient(40% 48% at 20% 28%, rgba(217,217,217,0.85), transparent 62%)",
        "radial-gradient(44% 54% at 82% 30%, rgba(240,240,240,0.95), transparent 66%)",
        "radial-gradient(46% 56% at 60% 82%, rgba(217,217,217,0.75), transparent 60%)",
        "radial-gradient(52% 62% at 12% 84%, rgba(240,240,240,0.85), transparent 66%)",
        "linear-gradient(130deg, #d9d9d9 0%, #e9e9e9 55%, #f0f0f0 100%)",
      ].join(", "),
      size: SIZE,
    },
  },
  // Dark — a deep purple aurora between rgb(20,2,36) and rgb(34,10,57); light text, dark glass.
  dark: {
    mode: "dark",
    primary: "#c4b5fd",
    primarySoft: "rgba(196,181,253,0.18)",
    contrast: "#1d0235",
    glass: "rgba(40,16,72,0.55)",
    glassBorder: "rgba(255,255,255,0.12)",
    lineStrong: "rgba(255,255,255,0.22)",
    text: {
      primary: "rgba(255,255,255,0.92)",
      secondary: "rgba(255,255,255,0.66)",
      disabled: "rgba(255,255,255,0.40)",
    },
    divider: "rgba(255,255,255,0.14)",
    signifier: DARK_SIGNIFIER,
    chip: {
      periwinkle: { main: "#9a9aff", soft: "rgba(105,105,255,0.20)" },
      aqua: { main: "#34d6e8", soft: "rgba(52,214,232,0.18)" },
      violet: { main: "#cf8bff", soft: "rgba(155,48,212,0.24)" },
      magenta: { main: "#f472d0", soft: "rgba(244,114,208,0.20)" },
      slate: { main: "#a3accd", soft: "rgba(95,106,148,0.22)" },
      steel: { main: "#8ac2cc", soft: "rgba(76,127,139,0.20)" },
    },
    aurora: {
      base: "#140224",
      image: [
        // the lighter-purple pools are dialed back so the field reads as a calm gradient between the
        // two endpoints rather than bright blotches over the dark base
        "radial-gradient(40% 48% at 20% 28%, rgba(34,10,57,0.45), transparent 62%)",
        "radial-gradient(44% 54% at 82% 30%, rgba(20,2,36,0.90), transparent 66%)",
        "radial-gradient(46% 56% at 60% 82%, rgba(34,10,57,0.42), transparent 60%)",
        "radial-gradient(52% 62% at 12% 84%, rgba(20,2,36,0.88), transparent 66%)",
        "linear-gradient(130deg, #140224 0%, #1c0630 55%, #220a39 100%)",
      ].join(", "),
      size: SIZE,
    },
  },
};

function buildTokens(variant: AuroraVariant) {
  const v = VARIANTS[variant];
  return {
    radius: 12,
    ...typeface,
    ...v.signifier,
    variant,
    primary: v.primary,
    glass: v.glass,
    lineStrong: v.lineStrong,
    aurora: v.aurora,
  };
}
type Tokens = ReturnType<typeof buildTokens>;

export function makeTheme(variant: AuroraVariant): Theme {
  const v = VARIANTS[variant];
  const tokens = buildTokens(variant);
  const heading = { fontFamily: typeface.heading } as const;
  const sig = v.signifier;

  return createTheme({
    palette: {
      mode: v.mode,
      primary: { main: v.primary, light: v.primarySoft, contrastText: v.contrast },
      success: { main: sig.green, light: sig.greenSoft },
      warning: { main: sig.amber, light: sig.amberSoft },
      error: { main: sig.red, light: sig.redSoft },
      info: { main: sig.blue, light: sig.blueSoft },
      periwinkle: { main: v.chip.periwinkle.main, light: v.chip.periwinkle.soft, contrastText: v.contrast },
      aqua: { main: v.chip.aqua.main, light: v.chip.aqua.soft, contrastText: v.contrast },
      violet: { main: v.chip.violet.main, light: v.chip.violet.soft, contrastText: v.contrast },
      magenta: { main: v.chip.magenta.main, light: v.chip.magenta.soft, contrastText: v.contrast },
      slate: { main: v.chip.slate.main, light: v.chip.slate.soft, contrastText: v.contrast },
      steel: { main: v.chip.steel.main, light: v.chip.steel.soft, contrastText: v.contrast },
      text: v.text,
      // default is transparent so content floats on the aurora; paper is the frosted-glass tint.
      background: { default: "transparent", paper: v.glass },
      divider: v.divider,
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
      // The base fill behind the fixed aurora layer (prevents flat overscroll edges).
      MuiCssBaseline: { styleOverrides: { body: { backgroundColor: v.aurora.base } } },
      // Every Paper becomes a frosted-glass panel — translucent, blurred, hairline-bordered — so the
      // aurora reads through it. This is what makes the boxes immersive rather than flat surfaces.
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: "none",
            backgroundColor: v.glass,
            backdropFilter: "blur(14px)",
            border: `1px solid ${v.glassBorder}`,
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

// Make `theme.tokens` type-safe in sx callbacks and styled(), and register the custom categorical-tag
// palette colors so `<Chip color="periwinkle" />` (etc.) typechecks.
declare module "@mui/material/styles" {
  interface Theme {
    tokens: Tokens;
  }
  interface ThemeOptions {
    tokens?: Tokens;
  }
  interface Palette {
    periwinkle: Palette["primary"];
    aqua: Palette["primary"];
    violet: Palette["primary"];
    magenta: Palette["primary"];
    slate: Palette["primary"];
    steel: Palette["primary"];
  }
  interface PaletteOptions {
    periwinkle?: PaletteOptions["primary"];
    aqua?: PaletteOptions["primary"];
    violet?: PaletteOptions["primary"];
    magenta?: PaletteOptions["primary"];
    slate?: PaletteOptions["primary"];
    steel?: PaletteOptions["primary"];
  }
}
declare module "@mui/material/Chip" {
  interface ChipPropsColorOverrides {
    periwinkle: true;
    aqua: true;
    violet: true;
    magenta: true;
    slate: true;
    steel: true;
  }
}
