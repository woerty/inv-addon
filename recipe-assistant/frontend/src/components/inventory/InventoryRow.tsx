import { memo, useState } from "react";
import {
  Box,
  Button,
  Checkbox,
  Chip,
  IconButton,
  TableCell,
  TableRow,
  Typography,
  styled,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import InventoryRestockButton from "../tracked/InventoryRestockButton";
import type { InventoryItem, TrackedProduct } from "../../types";

export type InventoryUpdate = {
  quantity?: number;
  storage_location?: string;
  expiration_date?: string;
};

type Draft = { quantity?: string; storage_location?: string; expiration_date?: string };

type Props = {
  item: InventoryItem;
  tracked: TrackedProduct | undefined;
  orderQty: number;
  /** Resolves true when the update went through, so the row drops its draft. */
  onSave: (barcode: string, data: InventoryUpdate) => Promise<boolean>;
  onDelete: (barcode: string) => void;
  onToggleSheet: (barcode: string, value: boolean) => void;
  onRelookup: (barcode: string) => void;
  onOpenTracked: (barcode: string, existing?: TrackedProduct) => void;
};

const dateFormat = new Intl.DateTimeFormat("de-DE");

/** A bare <input> styled like a small outlined TextField. The list renders
 *  three per row; a full TextField (FormControl, OutlinedInput, notched
 *  outline) made mounting ~300 rows more than twice as slow. */
const CellInput = styled("input")(({ theme }) => ({
  boxSizing: "border-box",
  height: 40,
  padding: "8.5px 14px",
  font: "inherit",
  fontSize: theme.typography.body1.fontSize,
  color: theme.palette.text.primary,
  colorScheme: theme.palette.mode,
  background: "transparent",
  border: "1px solid rgba(255, 255, 255, 0.23)",
  borderRadius: theme.shape.borderRadius,
  outline: "none",
  "&:hover": { borderColor: theme.palette.text.primary },
  "&:focus": {
    borderColor: theme.palette.primary.main,
    boxShadow: `inset 0 0 0 1px ${theme.palette.primary.main}`,
  },
}));

/** OpenFoodFacts serves 100/200/400px variants; the list shows 44px. */
const thumbnailUrl = (url: string) =>
  url.includes("openfoodfacts.org") || url.includes("openbeautyfacts.org")
    ? url.replace(/\.400\.jpg$/, ".100.jpg")
    : url;

const InventoryRow = ({
  item,
  tracked,
  orderQty,
  onSave,
  onDelete,
  onToggleSheet,
  onRelookup,
  onOpenTracked,
}: Props) => {
  const [draft, setDraft] = useState<Draft>({});
  const dirty = Object.keys(draft).length > 0;

  const setField = (field: keyof Draft, value: string) =>
    setDraft((prev) => ({ ...prev, [field]: value }));

  const handleSave = async () => {
    const data: InventoryUpdate = {};
    if (draft.quantity !== undefined) {
      const qty = parseInt(draft.quantity, 10);
      if (isNaN(qty) || qty < 0) return;
      if (qty === 0 && !window.confirm("Artikel wirklich löschen?")) return;
      data.quantity = qty;
    }
    if (draft.storage_location !== undefined) data.storage_location = draft.storage_location;
    if (draft.expiration_date !== undefined) data.expiration_date = draft.expiration_date;

    if (await onSave(item.barcode, data)) setDraft({});
  };

  return (
    <TableRow
      sx={{
        ...(item.quantity === 0 && {
          backgroundColor: "rgba(219, 68, 55, 0.14)",
        }),
      }}
    >
      <TableCell>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {item.image_url && (
            <Box
              component="img"
              src={thumbnailUrl(item.image_url)}
              alt=""
              loading="lazy"
              decoding="async"
              sx={{ width: 44, height: 44, objectFit: "contain", flexShrink: 0, borderRadius: 1 }}
            />
          )}
          <span>
            {item.name}
            {item.name === "Unbekanntes Produkt" && (
              <IconButton size="small" onClick={() => onRelookup(item.barcode)} title="Nochmal nachschlagen">
                <RefreshIcon fontSize="small" />
              </IconButton>
            )}
          </span>
        </Box>
      </TableCell>
      <TableCell>{item.barcode}</TableCell>
      <TableCell>
        <CellInput
          type="number"
          style={{ width: 80 }}
          value={draft.quantity ?? item.quantity}
          onChange={(e) => setField("quantity", e.target.value)}
        />
        {orderQty > 0 && (
          <Chip label={`${orderQty} in Bestellung`} size="small" color="warning" sx={{ mt: 0.5 }} />
        )}
        {item.quantity === 0 && tracked && (
          <Typography
            variant="caption"
            color={orderQty > 0 ? "warning.main" : "error"}
            display="block"
            sx={{ mt: 0.5 }}
          >
            {orderQty > 0 ? "in Bestellung" : "leer, nachbestellen"}
          </Typography>
        )}
      </TableCell>
      <TableCell>{item.category}</TableCell>
      <TableCell>{dateFormat.format(new Date(item.added_date))}</TableCell>
      <TableCell>
        <CellInput
          style={{ width: 130 }}
          value={draft.storage_location ?? item.storage_location?.name ?? ""}
          onChange={(e) => setField("storage_location", e.target.value)}
        />
      </TableCell>
      <TableCell>
        <CellInput
          type="date"
          style={{ width: 150 }}
          value={draft.expiration_date ?? item.expiration_date ?? ""}
          onChange={(e) => setField("expiration_date", e.target.value)}
        />
      </TableCell>
      <TableCell>
        <Checkbox
          checked={item.include_in_sheet}
          onChange={(e) => onToggleSheet(item.barcode, e.target.checked)}
        />
      </TableCell>
      <TableCell sx={{ whiteSpace: "nowrap" }}>
        <Button variant="contained" size="small" sx={{ mr: 1 }} onClick={handleSave} disabled={!dirty}>
          Speichern
        </Button>
        <Button variant="outlined" color="error" size="small" onClick={() => onDelete(item.barcode)}>
          Löschen
        </Button>
      </TableCell>
      <TableCell>
        <InventoryRestockButton tracked={tracked} onClick={() => onOpenTracked(item.barcode, tracked)} />
      </TableCell>
    </TableRow>
  );
};

export default memo(InventoryRow);
