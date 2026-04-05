import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from "@mui/material";
import type { PicnicSearchResult, TrackedProductCreate } from "../../types";

type Props = {
  product: PicnicSearchResult | null;
  onClose: () => void;
  onSubmit: (data: TrackedProductCreate) => Promise<void>;
};

const SubscribeDialog = ({ product, onClose, onSubmit }: Props) => {
  const [minQty, setMinQty] = useState(1);
  const [targetQty, setTargetQty] = useState(4);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (product) {
      setMinQty(1);
      setTargetQty(4);
      setError(null);
    }
  }, [product]);

  const targetInvalid = targetQty <= minQty;
  const canSubmit = useMemo(
    () => !submitting && minQty >= 0 && targetQty > 0 && !targetInvalid,
    [submitting, minQty, targetQty, targetInvalid]
  );

  const handleSubmit = async () => {
    if (!product || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        picnic_id: product.picnic_id,
        name: product.name,
        min_quantity: minQty,
        target_quantity: targetQty,
      });
      onClose();
    } catch (e) {
      const msg =
        e instanceof Error && e.message === "already_tracked"
          ? "Bereits abonniert"
          : e instanceof Error
            ? e.message
            : "Fehler";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={product !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Abonnieren: {product?.name}</DialogTitle>
      <DialogContent>
        <Box display="flex" flexDirection="column" gap={2} mt={1}>
          <TextField
            label="Mindestmenge"
            type="number"
            value={minQty}
            onChange={(e) => setMinQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 0 }}
            fullWidth
          />
          <TextField
            label="Ziel-Menge"
            type="number"
            value={targetQty}
            onChange={(e) => setTargetQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 1 }}
            helperText={
              targetInvalid
                ? "Ziel-Menge muss größer als die Mindestmenge sein"
                : "Auf diese Menge wird bei Unterschreitung aufgefüllt"
            }
            error={targetInvalid}
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button variant="contained" disabled={!canSubmit} onClick={handleSubmit}>
          Abonnieren
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SubscribeDialog;
