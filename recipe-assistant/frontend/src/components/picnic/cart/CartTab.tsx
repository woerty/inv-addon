import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Snackbar,
  Stack,
  Typography,
} from "@mui/material";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import CartItemComponent from "./CartItem";
import SlotPicker from "./SlotPicker";
import { useDeliverySlots } from "../../../hooks/useDeliverySlots";
import { checkout } from "../../../api/client";
import type { Cart } from "../../../types";
import { formatPrice } from "../../../utils/format";

interface CartTabProps {
  cart: Cart | null;
  loading: boolean;
  onAdd: (picnicId: string, count?: number) => Promise<void>;
  onRemove: (picnicId: string, count: number) => Promise<void>;
  onClear: () => Promise<void>;
  onProductClick: (picnicId: string) => void;
  onOrderPlaced?: () => void;
}

export default function CartTab({ cart, loading, onAdd, onRemove, onClear, onProductClick, onOrderPlaced }: CartTabProps) {
  const hasItems = !!cart && cart.items.length > 0;
  const { slots, selectedSlotId, loading: slotsLoading, select } = useDeliverySlots(hasItems);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (loading) {
    return <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>;
  }

  if (!cart || cart.items.length === 0) {
    return <Typography color="text.secondary" textAlign="center" py={4}>Dein Warenkorb ist leer</Typography>;
  }

  const handleAdd = async (picnicId: string) => { await onAdd(picnicId, 1); };

  const selectedSlot = slots.find(s => s.slot_id === selectedSlotId) ?? null;
  const mov = selectedSlot?.minimum_order_value_cents ?? null;
  const belowMov = mov != null && cart.total_price_cents < mov;
  const canOrder = !!selectedSlotId && !belowMov && !placing;

  const handlePlaceOrder = async () => {
    setPlacing(true);
    setError(null);
    try {
      await checkout();
      setConfirmOpen(false);
      setSuccess(true);
      onOrderPlaced?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bestellung fehlgeschlagen");
    } finally {
      setPlacing(false);
    }
  };

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
      <Box sx={{ mt: 1, display: "flex", justifyContent: "flex-end" }}>
        <Button variant="outlined" color="error" startIcon={<DeleteSweepIcon />} onClick={onClear} size="small">
          Warenkorb leeren
        </Button>
      </Box>

      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle1" fontWeight={600} sx={{ px: 1 }}>Liefermoment wählen</Typography>
      <Box sx={{ px: 1 }}>
        <SlotPicker slots={slots} selectedSlotId={selectedSlotId} loading={slotsLoading} disabled={placing} onSelect={select} />
      </Box>

      {belowMov && mov != null && (
        <Alert severity="info" sx={{ mt: 1 }}>
          Mindestbestellwert {formatPrice(mov)} – es fehlen noch {formatPrice(mov - cart.total_price_cents)}.
        </Alert>
      )}
      {error && <Alert severity="error" sx={{ mt: 1 }} onClose={() => setError(null)}>{error}</Alert>}

      <Box sx={{ mt: 2 }}>
        <Button variant="contained" fullWidth size="large" disabled={!canOrder} onClick={() => setConfirmOpen(true)}>
          Jetzt bestellen
        </Button>
      </Box>

      <Dialog open={confirmOpen} onClose={() => !placing && setConfirmOpen(false)}>
        <DialogTitle>Verbindlich bestellen?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {cart.total_items} Artikel für {formatPrice(cart.total_price_cents)} verbindlich bei Picnic bestellen?
            Diese Aktion kann nicht rückgängig gemacht werden.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)} disabled={placing}>Abbrechen</Button>
          <Button onClick={handlePlaceOrder} variant="contained" disabled={placing}>
            {placing ? <CircularProgress size={20} /> : "Bestellen"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={success}
        autoHideDuration={5000}
        onClose={() => setSuccess(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="success" onClose={() => setSuccess(false)}>Bestellung aufgegeben!</Alert>
      </Snackbar>
    </Box>
  );
}
