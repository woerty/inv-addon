import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import App from "./App";

const theme = createTheme({
  palette: {
    // Hardcoded to match Home Assistant's default DARK theme. The add-on is
    // shown through HA Ingress in an iframe, which cannot inherit HA's live
    // theme CSS variables, so we mirror HA's default-dark tokens here.
    mode: "dark",
    primary: { main: "#03a9f4", light: "#b3e5fc", dark: "#0288d1" },
    secondary: { main: "#ff9800", light: "#ffb74d", dark: "#f57c00" },
    success: { main: "#43a047" },
    warning: { main: "#ffa600" },
    error: { main: "#db4437" },
    info: { main: "#039be5" },
    background: {
      default: "#111111",
      paper: "#1c1c1c",
    },
    text: {
      primary: "#e1e1e1",
      secondary: "#9b9b9b",
    },
    divider: "rgba(225, 225, 225, 0.12)",
  },
  typography: {
    h4: { fontWeight: 700 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
    subtitle2: { fontWeight: 600, textTransform: "uppercase" as const, fontSize: "0.75rem", letterSpacing: "0.08em" },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { backgroundImage: "none" },
        outlined: ({ theme }) => ({ borderColor: theme.palette.divider }),
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none" as const, fontWeight: 600, borderRadius: 8 },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600 },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: ({ theme }) => ({ fontWeight: 700, backgroundColor: theme.palette.action.hover }),
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: { textTransform: "none" as const, fontWeight: 600 },
      },
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
