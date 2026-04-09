import { Paper, Typography } from "@mui/material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { ConsumptionTrend as TrendData } from "../../types";

const COLORS = ["#5c6bc0", "#26a69a", "#ff9800", "#ef5350", "#ab47bc", "#42a5f5"];

const formatDate = (ts: number) =>
  new Date(ts).toLocaleDateString("de-DE", { day: "numeric", month: "numeric" });

interface Props {
  trend: TrendData;
}

export default function ConsumptionTrend({ trend }: Props) {
  const chartData = trend.labels.map((label, i) => {
    const point: Record<string, number> = { time: new Date(label).getTime() };
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
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
            <XAxis
              dataKey="time"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={formatDate}
              tick={{ fontSize: 12 }}
            />
            <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
            <Tooltip
              labelFormatter={(ts) => new Date(ts as number).toLocaleDateString("de-DE", {
                weekday: "short", day: "numeric", month: "long",
              })}
            />
            <Legend />
            {trend.series.map((s, i) => (
              <Line
                key={s.category}
                type="monotone"
                dataKey={s.category}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={{ r: 2 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
