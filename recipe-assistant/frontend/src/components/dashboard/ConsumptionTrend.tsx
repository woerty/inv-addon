import { Paper, Typography } from "@mui/material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { ConsumptionTrend as TrendData } from "../../types";

const COLORS = ["#5c6bc0", "#26a69a", "#ff9800", "#ef5350", "#ab47bc", "#42a5f5"];

interface Props {
  trend: TrendData;
}

export default function ConsumptionTrend({ trend }: Props) {
  const chartData = trend.labels.map((label, i) => {
    const point: Record<string, string | number> = { week: label };
    for (const s of trend.series) {
      point[s.category] = s.data[i] ?? 0;
    }
    return point;
  });

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Verbrauchstrend
      </Typography>
      {chartData.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Keine Daten im Zeitraum</Typography>
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="week" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            {trend.series.map((s, i) => (
              <Line
                key={s.category}
                type="monotone"
                dataKey={s.category}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
