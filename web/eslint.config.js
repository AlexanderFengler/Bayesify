import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

// Flat config for the Vite + React + TS frontend. Rules are non-type-aware (fast; the `tsc -b` build
// already does full type checking, in CI too). `eslint-config-prettier` is applied LAST so it turns
// off every stylistic rule — Prettier owns formatting, ESLint owns correctness + hooks, and the two
// never fight.
export default tseslint.config(
  { ignores: ["dist"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Fast-refresh only reliably updates a module that exports components alone; a constant export
      // (e.g. a small enum/config) is safe, so allow that but warn on mixed component + logic exports.
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  prettier,
);
