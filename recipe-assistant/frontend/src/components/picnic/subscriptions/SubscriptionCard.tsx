import { Box, Card, CardContent, Chip, IconButton, Stack, Typography } from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import type { TrackedProduct } from "../../../types";

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/small.png`
    : undefined;

interface SubscriptionCardProps {
  item: TrackedProduct;
  onOrder: number;
  onEdit: (item: TrackedProduct) => void;
  onDelete: (item: TrackedProduct) => void;
}

type ThresholdStatus = "ok" | "on_order" | "critical";

function getStatus(item: TrackedProduct, onOrder: number): ThresholdStatus {
  if (item.current_quantity >= item.min_quantity) return "ok";
  if (onOrder > 0) return "on_order";
  return "critical";
}

const statusColor: Record<ThresholdStatus, "success" | "warning" | "error"> = {
  ok: "success", on_order: "warning", critical: "error",
};

const statusLabel: Record<ThresholdStatus, string> = {
  ok: "Auf Lager", on_order: "In Bestellung", critical: "Nachbestellen",
};

export default function SubscriptionCard({ item, onOrder, onEdit, onDelete }: SubscriptionCardProps) {
  const status = getStatus(item, onOrder);
  return (
    <Card variant="outlined" sx={{ mb: 1 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          {item.picnic_image_id && (
            <Box component="img" src={imgUrl(item.picnic_image_id)} alt={item.name}
              sx={{ width: 48, height: 48, objectFit: "contain" }} />
          )}
          <Box flex={1} minWidth={0}>
            <Typography variant="body1" fontWeight={500} noWrap>
              {item.picnic_name || item.name}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
              <Typography variant="caption" color="text.secondary">
                Bestand: {item.current_quantity} · Min: {item.min_quantity} · Ziel: {item.target_quantity}
              </Typography>
              {onOrder > 0 && <Chip label={`${onOrder} in Bestellung`} size="small" color="warning" />}
            </Stack>
          </Box>
          <Chip label={statusLabel[status]} size="small" color={statusColor[status]} />
          <IconButton size="small" onClick={() => onEdit(item)}><EditIcon fontSize="small" /></IconButton>
          <IconButton size="small" onClick={() => onDelete(item)} color="error"><DeleteIcon fontSize="small" /></IconButton>
        </Stack>
      </CardContent>
    </Card>
  );
}
