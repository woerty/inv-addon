import { Box, Paper, Typography } from "@mui/material";
import HistoryIcon from "@mui/icons-material/History";
import type { ActivityEntry } from "../../types";

const ACTION_LABELS: Record<string, string> = {
  "add": "hinzugef\u00fcgt",
  "remove": "entnommen",
  "scan-out": "gescannt (raus)",
  "scan-in": "gescannt (rein)",
  "restock_auto": "auto-nachbestellt",
  "delete": "gel\u00f6scht",
  "update": "aktualisiert",
};

const ACTION_COLORS: Record<string, string> = {
  "add": "#4caf50",
  "scan-in": "#4caf50",
  "restock_auto": "#4caf50",
  "remove": "#f44336",
  "scan-out": "#f44336",
  "delete": "#f44336",
  "update": "#9e9e9e",
};

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `vor ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `vor ${hours}h`;
  const days = Math.floor(hours / 24);
  return `vor ${days}d`;
}

interface Props {
  entries: ActivityEntry[];
}

export default function RecentActivity({ entries }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", overflow: "auto", maxHeight: 300, borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <HistoryIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Letzte Aktivit\u00e4t</Typography>
      </Box>
      {entries.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Keine Aktivit\u00e4ten im Zeitraum
        </Typography>
      )}
      {entries.map((e, i) => (
        <Box
          key={i}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            py: 0.5,
            px: 0.5,
            bgcolor: i % 2 === 0 ? "transparent" : "action.hover",
            borderRadius: 0.5,
          }}
        >
          <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: ACTION_COLORS[e.action] ?? "#9e9e9e", flexShrink: 0, mt: 0.2 }} />
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {e.product_name} {ACTION_LABELS[e.action] ?? e.action}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1, whiteSpace: "nowrap" }}>
            {timeAgo(e.timestamp)}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
