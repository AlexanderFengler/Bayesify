import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { theme } from "./theme";
import "./styles.css";

// CssBaseline applies MUI's reset and pulls body background/font from the theme. Its values are the
// same tokens styles.css already uses (background #f6f7f9, the same font stack), so the legacy
// screens are unaffected; it's mounted now because the new MUI landing shell relies on it. As more
// screens migrate, styles.css shrinks toward nothing and this stays the single baseline.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
