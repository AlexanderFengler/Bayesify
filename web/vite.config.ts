import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

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
});
