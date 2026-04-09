import { Box, Paper, Typography } from "@mui/material";
import LocalShippingIcon from "@mui/icons-material/LocalShipping";
import type { PendingOrder, Cart } from "../../types";

interface Props {
  orders: PendingOrder[];
  cart: Cart | null;
}

export default function PendingOrders({ orders, cart }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%", borderRadius: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
        <LocalShippingIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="subtitle2" color="text.secondary">Laufende Bestellungen</Typography>
      </Box>
      {orders.map((o) => (
        <Box key={o.delivery_id} sx={{ bgcolor: "action.hover", borderRadius: 1, p: 1, mb: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <Typography variant="body2">
              {o.delivery_time
                ? `Lieferung ${new Date(o.delivery_time).toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "short" })}`
                : "Lieferung geplant"}
            </Typography>
            <Typography variant="caption" color={o.status === "COMPLETED" ? "success.main" : "warning.main"}>
              {o.status}
            </Typography>
          </Box>
          <Typography variant="caption" color="text.secondary">
            {o.total_items} Artikel
          </Typography>
        </Box>
      ))}
      {cart && cart.total_items > 0 && (
        <Box sx={{ bgcolor: "action.hover", borderRadius: 1, p: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <Typography variant="body2">Warenkorb</Typography>
            <Typography variant="caption" color="warning.main">Offen</Typography>
          </Box>
          <Typography variant="caption" color="text.secondary">
            {cart.total_items} Artikel · €{(cart.total_price_cents / 100).toFixed(2)}
          </Typography>
        </Box>
      )}
      {orders.length === 0 && (!cart || cart.total_items === 0) && (
        <Typography variant="body2" color="text.secondary">
          Keine offenen Bestellungen
        </Typography>
      )}
    </Paper>
  );
}

