import { Box, IconButton, Paper, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip, ResponsiveContainer } from "recharts";
import type { DashboardProductDetail } from "../../types";

interface Props {
  detail: DashboardProductDetail;
  onClose: () => void;
}

const formatDate = (ts: number) =>
  new Date(ts).toLocaleDateString("de-DE", { day: "numeric", month: "numeric" });

export default function ProductDetail({ detail, onClose }: Props) {
  const chartData = detail.history.map((h) => ({
    time: new Date(h.timestamp).getTime(),
    quantity: h.quantity_after,
  }));

  return (
    <Paper sx={{ p: 2, gridColumn: "1 / -1" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Box>
          <Typography variant="h6">{detail.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            Aktuell: {detail.current_quantity}
            {" · "}Verbrauch: ~{detail.stats.avg_per_week}×/Woche
            {detail.stats.estimated_days_remaining !== null && (
              <> · Reicht noch ~{detail.stats.estimated_days_remaining} Tage</>
            )}
          </Typography>
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </Box>

      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
            <XAxis
              dataKey="time"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={formatDate}
              tick={{ fontSize: 11 }}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              labelFormatter={(ts) => new Date(Number(ts)).toLocaleString("de-DE", {
                day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit"
              })}
            />
            <Line type="stepAfter" dataKey="quantity" stroke="#5c6bc0" strokeWidth={2} dot={{ r: 3 }} />
            {detail.min_quantity !== null && (
              <ReferenceLine y={detail.min_quantity} stroke="#f44336" strokeDasharray="6 3" label="min" />
            )}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">Keine Verlaufsdaten</Typography>
      )}

      <Box sx={{ display: "flex", gap: 3, mt: 2, pt: 1, borderTop: 1, borderColor: "divider", justifyContent: "center" }}>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">{detail.stats.total_consumed}</Typography>
          <Typography variant="caption" color="text.secondary">Verbraucht</Typography>
        </Box>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">{detail.stats.avg_per_week}/W</Typography>
          <Typography variant="caption" color="text.secondary">Ø Rate</Typography>
        </Box>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">{detail.stats.times_restocked}×</Typography>
          <Typography variant="caption" color="text.secondary">Nachbestellt</Typography>
        </Box>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">€{(detail.stats.total_cost_cents / 100).toFixed(2)}</Typography>
          <Typography variant="caption" color="text.secondary">Kosten</Typography>
        </Box>
      </Box>
    </Paper>
  );
}
