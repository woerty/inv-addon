import { Box, Paper, Typography } from "@mui/material";
import type { ActivityEntry } from "../../types";

const ACTION_LABELS: Record<string, string> = {
  "add": "hinzugefügt",
  "remove": "entnommen",
  "scan-out": "gescannt (raus)",
  "scan-in": "gescannt (rein)",
  "restock_auto": "auto-nachbestellt",
  "delete": "gelöscht",
  "update": "aktualisiert",
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
    <Paper sx={{ p: 2, height: "100%", overflow: "auto", maxHeight: 300 }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Letzte Aktivität
      </Typography>
      {entries.map((e, i) => (
        <Box key={i} sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
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
