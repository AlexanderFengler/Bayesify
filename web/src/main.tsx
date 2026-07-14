import React from "react";
import ReactDOM from "react-dom/client";
import "katex/dist/katex.min.css";
import { App } from "./App";
import { installGlobalErrorHandlers } from "./telemetry";
import { AppThemeProvider } from "./ThemeMode";
import "./styles.css";

// Catch uncaught errors + unhandled promise rejections (the ones React's ErrorBoundary never sees).
installGlobalErrorHandlers();

// AppThemeProvider holds the active aurora variant (teal default / indigo dark), builds the matching
// MUI dark theme, and applies CssBaseline. The whole app is light-on-dark, floating over the aurora.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppThemeProvider>
      <App />
    </AppThemeProvider>
  </React.StrictMode>,
);
