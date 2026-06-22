import { ThemeProvider } from "@mui/material/styles";
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { theme } from "./theme";
import "./styles.css";

// ThemeProvider only affects MUI components, so wrapping the app here has no effect on the existing
// CSS-styled screens — it just makes any MUI component we add render on-brand. CssBaseline (MUI's
// reset + default font) is intentionally NOT mounted yet; it'll come in with the new app shell so we
// don't disturb the current look while screens still rely on styles.css.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
