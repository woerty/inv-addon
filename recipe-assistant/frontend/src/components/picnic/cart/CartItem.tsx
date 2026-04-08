import { useState } from "react";
import { Box, IconButton, Stack, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import type { CartItem as CartItemType } from "../../../types";

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/small.png`
    : undefined;

const formatPrice = (cents: number | null) =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";

interface CartItemProps {
  item: CartItemType;
  onAdd: (picnicId: string) => Promise<void>;
  onRemove: (picnicId: string, count: number) => Promise<void>;
  onClick: (picnicId: string) => void;
}

export default function CartItem({ item, onAdd, onRemove, onClick }: CartItemProps) {
  const [busy, setBusy] = useState(false);

  const handleAdd = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try { await onAdd(item.picnic_id); } finally { setBusy(false); }
  };

  const handleRemove = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try { await onRemove(item.picnic_id, 1); } finally { setBusy(false); }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try { await onRemove(item.picnic_id, item.quantity); } finally { setBusy(false); }
  };

  return (
    <Stack
      direction="row" alignItems="center" spacing={1.5}
      sx={{ py: 1, px: 1, borderBottom: "1px solid", borderColor: "divider", cursor: "pointer" }}
      onClick={() => onClick(item.picnic_id)}
    >
      {item.image_id && (
        <Box component="img" src={imgUrl(item.image_id)} alt={item.name}
          sx={{ width: 48, height: 48, objectFit: "contain" }} />
      )}
      <Box flex={1} minWidth={0}>
        <Typography variant="body2" noWrap fontWeight={500}>{item.name}</Typography>
        <Typography variant="caption" color="text.secondary">
          {item.unit_quantity} {item.price_cents != null && `· ${formatPrice(item.price_cents)}`}
        </Typography>
      </Box>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        <IconButton size="small" onClick={handleRemove} disabled={busy}><RemoveIcon fontSize="small" /></IconButton>
        <Typography variant="body2" sx={{ minWidth: 24, textAlign: "center" }}>{item.quantity}</Typography>
        <IconButton size="small" onClick={handleAdd} disabled={busy}><AddIcon fontSize="small" /></IconButton>
        <IconButton size="small" onClick={handleDelete} disabled={busy} color="error"><DeleteOutlineIcon fontSize="small" /></IconButton>
      </Stack>
      <Typography variant="body2" fontWeight={600} sx={{ minWidth: 50, textAlign: "right" }}>
        {formatPrice(item.total_price_cents)}
      </Typography>
    </Stack>
  );
}
