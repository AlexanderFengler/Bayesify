import react from "@vitejs/plugin-react";
// defineConfig from vitest/config (not vite) so the `test` block below is typed.
import { defineConfig } from "vitest/config";

// Local-first dev: the SPA runs on :5173 and proxies /api to the FastAPI app on :8000.
// SSE (the progress stream) passes through the proxy unbuffered.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  // Vitest: jsdom so component tests can render; setup registers @testing-library/jest-dom matchers.
  // Tests import { describe, it, expect } explicitly (no globals), so no tsconfig types change needed.
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
