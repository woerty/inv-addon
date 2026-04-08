import { useEffect, useState } from "react";
import {
  Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle,
  IconButton, Stack, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import CloseIcon from "@mui/icons-material/Close";
import RepeatIcon from "@mui/icons-material/Repeat";
import { usePicnicProduct } from "../../../hooks/usePicnicProduct";

interface ProductDetailModalProps {
  picnicId: string | null;
  onClose: () => void;
  onCartAdd: (picnicId: string, count: number) => Promise<void>;
  onCartRemove: (picnicId: string, count: number) => Promise<void>;
  onSubscribe: (picnicId: string, name: string) => void;
}

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/large.png`
    : undefined;

const formatPrice = (cents: number | null) =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";

export default function ProductDetailModal({
  picnicId, onClose, onCartAdd, onCartRemove, onSubscribe,
}: ProductDetailModalProps) {
  const { product, loading, load, clear } = usePicnicProduct();
  const [addQty, setAddQty] = useState(1);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (picnicId) { load(picnicId); setAddQty(1); } else { clear(); }
  }, [picnicId, load, clear]);

  const handleAdd = async () => {
    if (!product) return;
    setBusy(true);
    try { await onCartAdd(product.picnic_id, addQty); load(product.picnic_id); }
    finally { setBusy(false); }
  };

  const handleRemove = async () => {
    if (!product) return;
    setBusy(true);
    try { await onCartRemove(product.picnic_id, 1); load(product.picnic_id); }
    finally { setBusy(false); }
  };

  const handleAddOne = async () => {
    if (!product) return;
    setBusy(true);
    try { await onCartAdd(product.picnic_id, 1); load(product.picnic_id); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={!!picnicId} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {product?.name ?? "Produkt"}
        <IconButton onClick={onClose} size="small"><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent>
        {loading ? (
          <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
        ) : product ? (
          <Stack spacing={2}>
            {product.image_id && (
              <Box display="flex" justifyContent="center" sx={{ bgcolor: "#fafafa", borderRadius: 1, p: 2 }}>
                <img src={imgUrl(product.image_id)} alt={product.name} style={{ maxHeight: 200, objectFit: "contain" }} />
              </Box>
            )}
            <Stack direction="row" spacing={1} alignItems="center">
              {product.unit_quantity && <Typography variant="body2" color="text.secondary">{product.unit_quantity}</Typography>}
              {product.price_cents != null && <Typography variant="h6">{formatPrice(product.price_cents)}</Typography>}
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {product.in_cart > 0 && <Chip label={`${product.in_cart} im Warenkorb`} color="primary" />}
              {product.on_order > 0 && <Chip label={`${product.on_order} in Bestellung`} color="warning" />}
              {product.inventory_quantity > 0 && <Chip label={`${product.inventory_quantity} im Inventar`} color="success" />}
            </Stack>
            {product.description && <Typography variant="body2" color="text.secondary">{product.description}</Typography>}
            {product.in_cart > 0 ? (
              <Stack direction="row" alignItems="center" spacing={1} justifyContent="center">
                <IconButton onClick={handleRemove} disabled={busy} color="primary"><RemoveIcon /></IconButton>
                <Typography variant="h6" sx={{ minWidth: 40, textAlign: "center" }}>{product.in_cart}</Typography>
                <IconButton onClick={handleAddOne} disabled={busy} color="primary"><AddIcon /></IconButton>
              </Stack>
            ) : (
              <Stack direction="row" alignItems="center" spacing={1}>
                <IconButton onClick={() => setAddQty(q => Math.max(1, q - 1))} disabled={addQty <= 1} size="small"><RemoveIcon /></IconButton>
                <Typography sx={{ minWidth: 30, textAlign: "center" }}>{addQty}</Typography>
                <IconButton onClick={() => setAddQty(q => q + 1)} size="small"><AddIcon /></IconButton>
                <Button variant="contained" onClick={handleAdd} disabled={busy} sx={{ flex: 1 }}>In den Warenkorb</Button>
              </Stack>
            )}
            {product.is_subscribed ? (
              <Chip icon={<RepeatIcon />} label="Abonniert" color="success" />
            ) : (
              <Button variant="outlined" startIcon={<RepeatIcon />} onClick={() => onSubscribe(product.picnic_id, product.name)}>Abonnieren</Button>
            )}
          </Stack>
        ) : (
          <Typography color="text.secondary">Produkt nicht gefunden</Typography>
        )}
      </DialogContent>
    </Dialog>
  );
}
