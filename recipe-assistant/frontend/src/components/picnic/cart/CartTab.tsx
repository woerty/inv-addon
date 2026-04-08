import { Box, Button, CircularProgress, Divider, Stack, Typography } from "@mui/material";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import CartItemComponent from "./CartItem";
import type { Cart } from "../../../types";

const formatPrice = (cents: number) => `€${(cents / 100).toFixed(2).replace(".", ",")}`;

interface CartTabProps {
  cart: Cart | null;
  loading: boolean;
  onAdd: (picnicId: string, count?: number) => Promise<void>;
  onRemove: (picnicId: string, count: number) => Promise<void>;
  onClear: () => Promise<void>;
  onProductClick: (picnicId: string) => void;
}

export default function CartTab({ cart, loading, onAdd, onRemove, onClear, onProductClick }: CartTabProps) {
  if (loading) {
    return <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>;
  }

  if (!cart || cart.items.length === 0) {
    return <Typography color="text.secondary" textAlign="center" py={4}>Dein Warenkorb ist leer</Typography>;
  }

  const handleAdd = async (picnicId: string) => { await onAdd(picnicId, 1); };

  return (
    <Box>
      {cart.items.map(item => (
        <CartItemComponent key={item.picnic_id} item={item} onAdd={handleAdd} onRemove={onRemove} onClick={onProductClick} />
      ))}
      <Divider sx={{ my: 2 }} />
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 1 }}>
        <Typography variant="body1">{cart.total_items} Artikel</Typography>
        <Typography variant="h6" fontWeight={600}>{formatPrice(cart.total_price_cents)}</Typography>
      </Stack>
      <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
        <Button variant="outlined" color="error" startIcon={<DeleteSweepIcon />} onClick={onClear} size="small">
          Warenkorb leeren
        </Button>
      </Box>
    </Box>
  );
}
