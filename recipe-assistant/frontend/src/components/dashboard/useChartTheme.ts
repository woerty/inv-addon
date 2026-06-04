import { useTheme } from "@mui/material";

/**
 * Recharts styling derived from the MUI theme. Recharts doesn't read the MUI
 * theme, so on the dark theme its default grey axis/grid/tooltip colours are
 * unreadable -- this maps them onto the current palette.
 */
export function useChartTheme() {
  const theme = useTheme();
  return {
    tickFill: theme.palette.text.secondary,
    lineStroke: theme.palette.divider,
    tooltip: {
      contentStyle: {
        backgroundColor: theme.palette.background.paper,
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 8,
      },
      labelStyle: { color: theme.palette.text.secondary },
      itemStyle: { color: theme.palette.text.primary },
    },
  };
}
