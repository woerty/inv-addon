import { useState } from "react";
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
import type { TrackedProduct } from "../../types";

type Props = {
  tracked: TrackedProduct | null;
  onClose: () => void;
  onPromote: (synthBarcode: string, newBarcode: string) => Promise<{ merged: boolean }>;
};

const PromoteBarcodeDialog = ({ tracked, onClose, onPromote }: Props) => {
  const [barcode, setBarcode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSynth = barcode.startsWith("picnic:");
  const canSubmit = barcode.trim().length > 0 && !isSynth && !submitting;

  const handleSubmit = async () => {
    if (!tracked || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onPromote(tracked.barcode, barcode.trim());
      onClose();
      setBarcode("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setBarcode("");
    setError(null);
    onClose();
  };

  return (
    <Dialog open={tracked !== null} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Barcode nachpflegen: {tracked?.name}</DialogTitle>
      <DialogContent>
        <Box display="flex" flexDirection="column" gap={2} mt={1}>
          <TextField
            label="Barcode scannen oder eingeben"
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) handleSubmit();
            }}
            autoFocus
            fullWidth
            error={isSynth}
            helperText={isSynth ? "Bitte einen echten Barcode eingeben" : undefined}
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Abbrechen</Button>
        <Button variant="contained" disabled={!canSubmit} onClick={handleSubmit}>
          Barcode zuweisen
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PromoteBarcodeDialog;
