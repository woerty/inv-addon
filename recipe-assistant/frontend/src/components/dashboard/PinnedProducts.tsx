import { Box, Paper, Typography } from "@mui/material";
import type { PinnedProduct } from "../../types";

function qtyColor(qty: number, min: number | null): string {
  if (qty === 0) return "error.main";
  if (min !== null && qty < min) return "error.main";
  if (min !== null && qty === min) return "warning.main";
  return "success.main";
}

interface Props {
  products: PinnedProduct[];
}

export default function PinnedProducts({ products }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Gepinnte Produkte
      </Typography>
      {products.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Keine Produkte gepinnt
        </Typography>
      )}
      {products.map((p) => (
        <Box key={p.barcode} sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {p.name}
          </Typography>
          <Typography variant="body2" fontWeight={600} color={qtyColor(p.quantity, p.min_quantity)}>
            {p.quantity}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
