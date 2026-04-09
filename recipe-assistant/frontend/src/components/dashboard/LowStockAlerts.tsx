import { Box, Paper, Typography } from "@mui/material";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import type { LowStockItem } from "../../types";

interface Props {
  items: LowStockItem[];
}

export default function LowStockAlerts({ items }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <WarningAmberIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Niedrig-Bestand</Typography>
      </Box>
      {items.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Alles ausreichend vorrätig
        </Typography>
      )}
      {items.map((item) => (
        <Box
          key={item.barcode}
          sx={{
            display: "flex",
            justifyContent: "space-between",
            py: 0.5,
            px: 1,
            borderLeft: "3px solid",
            borderColor: item.quantity === 0 ? "error.main" : "warning.main",
            bgcolor: item.quantity === 0 ? "error.50" : "warning.50",
            borderRadius: 1,
            mb: 0.5,
          }}
        >
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {item.name}
          </Typography>
          <Box>
            <Typography component="span" variant="body2" fontWeight={600} color="error.main">
              {item.quantity}
            </Typography>
            <Typography component="span" variant="caption" color="text.secondary">
              {" "}/ min {item.min_quantity}
            </Typography>
          </Box>
        </Box>
      ))}
    </Paper>
  );
}
