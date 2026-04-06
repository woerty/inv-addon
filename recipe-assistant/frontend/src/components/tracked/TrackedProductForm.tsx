import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from "@mui/material";
import { useResolvePreview } from "../../hooks/useTrackedProducts";
import type {
  TrackedProduct,
  TrackedProductCreate,
  TrackedProductUpdate,
} from "../../types";

type Mode = "create" | "edit";

type Props = {
  open: boolean;
  mode: Mode;
  initialBarcode?: string;
  existing?: TrackedProduct;
  onClose: () => void;
  onSubmitCreate: (data: TrackedProductCreate) => Promise<void>;
  onSubmitUpdate: (barcode: string, data: TrackedProductUpdate) => Promise<void>;
};

const DEBOUNCE_MS = 500;

const TrackedProductForm = ({
  open,
  mode,
  initialBarcode = "",
  existing,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
}: Props) => {
  const [barcode, setBarcode] = useState(initialBarcode);
  const [minQty, setMinQty] = useState<number>(existing?.min_quantity ?? 1);
  const [targetQty, setTargetQty] = useState<number>(
    existing?.target_quantity ?? 4
  );
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { preview, loading: previewLoading, resolve, clear } = useResolvePreview();

  // Reset internal state whenever we reopen the dialog.
  useEffect(() => {
    if (open) {
      setBarcode(existing?.barcode ?? initialBarcode);
      setMinQty(existing?.min_quantity ?? 1);
      setTargetQty(existing?.target_quantity ?? 4);
      setSubmitError(null);
      if (mode === "edit" && existing) {
        // Edit mode: barcode is fixed and Picnic mapping is locked in; skip
        // the preview call and synthesize a resolved state from the row.
        // (The preview state is used only to show the Picnic name/image.)
        clear();
      }
    }
  }, [open, mode, existing, initialBarcode, clear]);

  // Debounced live Picnic resolution on barcode change (create mode only).
  useEffect(() => {
    if (mode !== "create" || !barcode.trim()) {
      clear();
      return;
    }
    const handle = setTimeout(() => {
      resolve(barcode.trim());
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [barcode, mode, resolve, clear]);

  const targetInvalid = targetQty < minQty;
  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (minQty < 0) return false;
    if (targetQty <= 0 || targetInvalid) return false;
    if (mode === "edit") return true;
    return preview?.resolved === true;
  }, [mode, preview, minQty, targetQty, targetInvalid, submitting]);

  const handleSubmit = async () => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (mode === "create") {
        await onSubmitCreate({
          barcode: barcode.trim(),
          min_quantity: minQty,
          target_quantity: targetQty,
        });
      } else if (existing) {
        await onSubmitUpdate(existing.barcode, {
          min_quantity: minQty,
          target_quantity: targetQty,
        });
      }
      onClose();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Fehler beim Speichern");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {mode === "create"
          ? "Nachbestellungs-Regel anlegen"
          : "Nachbestellungs-Regel bearbeiten"}
      </DialogTitle>
      <DialogContent>
        <Box display="flex" flexDirection="column" gap={2} mt={1}>
          <TextField
            label="Barcode"
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            disabled={mode === "edit"}
            fullWidth
          />

          {mode === "create" && (
            <Box>
              {previewLoading && (
                <Box display="flex" alignItems="center" gap={1}>
                  <CircularProgress size={16} />
                  <Typography variant="body2">
                    Picnic-Verfügbarkeit wird geprüft…
                  </Typography>
                </Box>
              )}
              {!previewLoading && preview?.resolved && (
                <Alert severity="success">
                  Gefunden: {preview.picnic_name}
                  {preview.picnic_unit_quantity
                    ? ` (${preview.picnic_unit_quantity})`
                    : ""}
                </Alert>
              )}
              {!previewLoading &&
                preview !== null &&
                preview.resolved === false && (
                  <Alert severity="error">
                    Nicht bei Picnic verfügbar — Regel kann nicht angelegt
                    werden.
                  </Alert>
                )}
            </Box>
          )}

          {mode === "edit" && existing && (
            <Alert severity="info">
              {existing.picnic_name}
              {existing.picnic_unit_quantity
                ? ` (${existing.picnic_unit_quantity})`
                : ""}
            </Alert>
          )}

          <TextField
            label="Mindestmenge (min_quantity)"
            type="number"
            value={minQty}
            onChange={(e) => setMinQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 0 }}
            fullWidth
          />
          <TextField
            label="Ziel-Menge (target_quantity)"
            type="number"
            value={targetQty}
            onChange={(e) => setTargetQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 1 }}
            helperText={
              targetInvalid
                ? "Ziel-Menge darf nicht kleiner als die Mindestmenge sein"
                : "Auf diese Menge wird bei Unterschreitung aufgefüllt"
            }
            error={targetInvalid}
            fullWidth
          />

          {submitError && <Alert severity="error">{submitError}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button
          variant="contained"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          Speichern
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default TrackedProductForm;
