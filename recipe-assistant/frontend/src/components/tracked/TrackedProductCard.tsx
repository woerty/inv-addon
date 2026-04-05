import {
  Box,
  Button,
  Chip,
  IconButton,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import QrCodeScannerIcon from "@mui/icons-material/QrCodeScanner";
import type { TrackedProduct } from "../../types";

type Props = {
  item: TrackedProduct;
  onEdit: (item: TrackedProduct) => void;
  onDelete: (item: TrackedProduct) => void;
  onPromote?: (item: TrackedProduct) => void;
};

const TrackedProductCard = ({ item, onEdit, onDelete, onPromote }: Props) => {
  const badgeColor = item.below_threshold ? "error" : "success";
  const isSynthetic = item.barcode.startsWith("picnic:");

  return (
    <Paper sx={{ p: 2, mb: 1 }}>
      <Stack direction="row" spacing={2} alignItems="center">
        {item.picnic_image_id && (
          <Box
            component="img"
            src={`https://storefront-prod.nl.picnicinternational.com/static/images/${item.picnic_image_id}/medium.png`}
            alt=""
            sx={{ width: 56, height: 56, objectFit: "contain" }}
          />
        )}
        <Box flex={1}>
          <Typography variant="subtitle1">{item.picnic_name}</Typography>
          {item.picnic_unit_quantity && (
            <Typography variant="body2" color="text.secondary">
              {item.picnic_unit_quantity}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary">
            Auffüllen auf {item.target_quantity}
          </Typography>
        </Box>
        <Chip
          label={`${item.current_quantity} / ${item.min_quantity}`}
          color={badgeColor}
          size="small"
        />
        {isSynthetic && (
          <Chip label="Picnic-only" size="small" color="info" />
        )}
        {isSynthetic && onPromote && (
          <Button
            size="small"
            startIcon={<QrCodeScannerIcon />}
            onClick={() => onPromote(item)}
          >
            Barcode scannen
          </Button>
        )}
        <IconButton onClick={() => onEdit(item)} size="small">
          <EditIcon fontSize="small" />
        </IconButton>
        <IconButton onClick={() => onDelete(item)} size="small">
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Paper>
  );
};

export default TrackedProductCard;
