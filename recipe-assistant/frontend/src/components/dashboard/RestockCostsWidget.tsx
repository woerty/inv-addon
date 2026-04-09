import { Box, Paper, Typography } from "@mui/material";
import EuroIcon from "@mui/icons-material/Euro";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { RestockCosts } from "../../types";

interface Props {
  costs: RestockCosts;
}

export default function RestockCostsWidget({ costs }: Props) {
  const diff = costs.previous_period_cents > 0
    ? Math.round((costs.total_cents - costs.previous_period_cents) / costs.previous_period_cents * 100)
    : 0;

  const chartData = costs.weekly.map((w) => ({ week: w.week, euro: w.cents / 100 }));

  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <EuroIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Restock-Kosten</Typography>
      </Box>
      <Box sx={{ textAlign: "center", mb: 1 }}>
        <Typography variant="h5" fontWeight={700}>
          €{(costs.total_cents / 100).toFixed(2)}
        </Typography>
        {diff !== 0 && (
          <Typography variant="caption" color={diff < 0 ? "success.main" : "error.main"}>
            {diff > 0 ? "↑" : "↓"} {Math.abs(diff)}% vs. Vorperiode
          </Typography>
        )}
      </Box>
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={chartData}>
            <XAxis dataKey="week" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v) => `€${Number(v ?? 0).toFixed(2)}`} />
            <Bar dataKey="euro" fill="#5c6bc0" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
