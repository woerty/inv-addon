import { Box, CircularProgress, Divider, Typography } from "@mui/material";
import type { PendingOrder } from "../../../types";
import OrderCard from "./OrderCard";
import ImportSection from "./ImportSection";

interface OrdersTabProps {
  orders: PendingOrder[];
  loading: boolean;
}

export default function OrdersTab({ orders, loading }: OrdersTabProps) {
  return (
    <Box>
      <Typography variant="h6" gutterBottom>Laufende Bestellungen</Typography>
      {loading ? (
        <Box display="flex" justifyContent="center" py={2}><CircularProgress /></Box>
      ) : orders.length === 0 ? (
        <Typography color="text.secondary" sx={{ mb: 2 }}>Keine laufenden Bestellungen</Typography>
      ) : (
        <Box sx={{ mb: 3 }}>
          {orders.map(order => <OrderCard key={order.delivery_id} order={order} />)}
        </Box>
      )}
      <Divider sx={{ my: 3 }} />
      <Typography variant="h6" gutterBottom>Lieferungen importieren</Typography>
      <ImportSection />
    </Box>
  );
}
