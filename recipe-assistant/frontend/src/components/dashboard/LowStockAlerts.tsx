import { Box, Paper, Typography } from "@mui/material";
import type { LowStockItem } from "../../types";

interface Props {
  items: LowStockItem[];
}

export default function LowStockAlerts({ items }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Niedrig-Bestand
      </Typography>
      {items.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Alles ausreichend vorrätig
        </Typography>
      )}
      {items.map((item) => (
        <Box key={item.barcode} sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
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
