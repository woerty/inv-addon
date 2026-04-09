import { Box, Chip, Paper, Typography } from "@mui/material";
import PushPinIcon from "@mui/icons-material/PushPin";
import type { PinnedProduct } from "../../types";

interface Props {
  products: PinnedProduct[];
}

export default function PinnedProducts({ products }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <PushPinIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Gepinnte Produkte</Typography>
      </Box>
      {products.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Keine Produkte gepinnt
        </Typography>
      )}
      {products.map((p) => (
        <Box key={p.barcode} sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", py: 0.5 }}>
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {p.name}
          </Typography>
          <Chip
            label={p.quantity}
            size="small"
            color={p.quantity === 0 ? "error" : (p.min_quantity !== null && p.quantity <= p.min_quantity) ? "warning" : "success"}
            variant="filled"
            sx={{ minWidth: 32, fontWeight: 600 }}
          />
        </Box>
      ))}
    </Paper>
  );
}
