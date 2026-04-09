import { Box, Paper, Typography } from "@mui/material";
import BarChartIcon from "@mui/icons-material/BarChart";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import type { TopConsumer } from "../../types";

interface Props {
  consumers: TopConsumer[];
  onSelect: (barcode: string) => void;
}

export default function TopConsumers({ consumers, onSelect }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <BarChartIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Top-Verbraucher</Typography>
      </Box>
      {consumers.length === 0 && (
        <Typography variant="body2" color="text.secondary">Keine Daten</Typography>
      )}
      {consumers.map((c, idx) => (
        <Box
          key={c.barcode}
          onClick={() => onSelect(c.barcode)}
          sx={{
            display: "flex", alignItems: "center", gap: 1, py: 0.5,
            cursor: "pointer", "&:hover": { bgcolor: "action.hover" }, borderRadius: 1, px: 0.5,
          }}
        >
          <Typography
            variant="body2"
            sx={{ width: 20, textAlign: "right", fontWeight: idx < 3 ? 700 : 400, color: idx < 3 ? "text.primary" : "text.secondary" }}
          >
            {idx + 1}.
          </Typography>
          <Typography variant="body2" noWrap sx={{ flex: 1, fontWeight: idx < 3 ? 600 : 400 }}>
            {c.name}
          </Typography>
          <Box sx={{ width: 50, height: 20 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={c.sparkline.map((v, i) => ({ v, i }))}>
                <Line type="monotone" dataKey="v" stroke="#5c6bc0" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ width: 32, textAlign: "right" }}>
            {c.count}x
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
