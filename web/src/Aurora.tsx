import { Box } from "@mui/material";

// The dynamic "aurora" background — a single fixed, full-viewport layer behind the entire app (Layout
// renders it once). Because it sits behind everything and the header/footer/panels/transitions are
// transparent or frosted glass, the living gradient is visible across the whole page at all times.
// Its colours come from the active theme variant (teal default / indigo dark), so toggling the theme
// re-paints it. Several over-sized radial pools drift over a base gradient, each on its own path so
// the colours merge and separate organically. Falls back to a flat fill for reduced-motion users.
// `fast` doubles the drift speed (used on the processing page, so the wait *feels* quicker).
export function Aurora({ fast = false }: { fast?: boolean }) {
  return (
    <Box
      aria-hidden
      sx={(t) => ({
        position: "fixed",
        inset: 0,
        zIndex: 0,
        pointerEvents: "none",
        backgroundColor: t.tokens.aurora.base,
        backgroundImage: t.tokens.aurora.image,
        backgroundSize: t.tokens.aurora.size,
        animation: `heroFlow ${fast ? 14 : 28}s ease-in-out infinite`,
        "@keyframes heroFlow": {
          "0%": { backgroundPosition: "0% 0%, 100% 50%, 50% 100%, 0% 100%, 0% 50%" },
          "50%": { backgroundPosition: "100% 100%, 0% 60%, 0% 0%, 100% 0%, 100% 50%" },
          "100%": { backgroundPosition: "0% 0%, 100% 50%, 50% 100%, 0% 100%, 0% 50%" },
        },
        "@media (prefers-reduced-motion: reduce)": { animation: "none" },
      })}
    />
  );
}
