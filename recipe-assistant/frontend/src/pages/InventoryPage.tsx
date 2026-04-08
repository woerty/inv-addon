import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Chip,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import FileUploadIcon from "@mui/icons-material/FileUpload";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import RefreshIcon from "@mui/icons-material/Refresh";
import LocalGroceryStoreIcon from "@mui/icons-material/LocalGroceryStore";
import { IconButton } from "@mui/material";
import { useInventory } from "../hooks/useInventory";
import { useNotification } from "../components/NotificationProvider";
import { exportData, importData, relookupBarcode, relookupAllUnknown, backfillImages } from "../api/client";
import { usePicnicStatus } from "../hooks/usePicnic";
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import InventoryRestockButton from "../components/tracked/InventoryRestockButton";
import TrackedProductForm from "../components/tracked/TrackedProductForm";
import type { TrackedProduct } from "../types";

type SortKey = "name" | "quantity" | "category" | "barcode" | "added_date";
type Order = "asc" | "desc";

const InventoryPage = () => {
  const inventory = useInventory();
  const { items, loading, refetch } = inventory;
  const { notify } = useNotification();
  const { status: picnicStatus } = usePicnicStatus();
  const navigate = useNavigate();

  const trackedProducts = useTrackedProducts();
  const trackedByBarcode = useMemo(() => {
    const map = new Map<string, TrackedProduct>();
    for (const tp of trackedProducts.items) {
      map.set(tp.barcode, tp);
    }
    return map;
  }, [trackedProducts.items]);

  const { quantityMap: orderQuantities } = usePicnicPendingOrders();
  const barcodeToOrderQty = useMemo(() => {
    const map: Record<string, number> = {};
    for (const tp of trackedProducts.items) {
      const qty = orderQuantities[tp.picnic_id];
      if (tp.picnic_id && qty) {
        map[tp.barcode] = qty;
      }
    }
    return map;
  }, [trackedProducts.items, orderQuantities]);

  const [trackedFormOpen, setTrackedFormOpen] = useState(false);
  const [trackedFormBarcode, setTrackedFormBarcode] = useState("");
  const [trackedFormExisting, setTrackedFormExisting] = useState<
    TrackedProduct | undefined
  >(undefined);

  const openTrackedForm = (barcode: string, existing?: TrackedProduct) => {
    setTrackedFormBarcode(barcode);
    setTrackedFormExisting(existing);
    setTrackedFormOpen(true);
  };

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Refetch every time this page is rendered (navigation back from scan, etc.)
  useEffect(() => {
    refetch();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState("");

  const handleExport = async () => {
    try {
      const blob = await exportData();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `inventar-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      notify("Export heruntergeladen", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Export fehlgeschlagen", "error");
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const result = await importData(file);
      notify(result.message, "success");
      refetch();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Import fehlgeschlagen", "error");
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleRelookupAll = async () => {
    try {
      const result = await relookupAllUnknown();
      notify(result.message, result.updated > 0 ? "success" : "info");
      if (result.updated > 0) refetch();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const handleBackfillImages = async () => {
    try {
      const result = await backfillImages();
      const d = result.diagnostics;
      const detail = d
        ? ` (Picnic GTIN: ${d.gtin_hit ?? 0}/${d.total ?? 0}, Search-Match: ${d.search_match ?? 0}, OFF: ${d.off_hit ?? 0}, Fehler: ${(d.gtin_err ?? 0) + (d.search_err ?? 0)})`
        : "";
      notify(result.message + detail, result.updated > 0 ? "success" : "info");
      if (result.updated > 0) refetch();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const handleRelookup = async (barcode: string) => {
    try {
      const result = await relookupBarcode(barcode);
      notify(result.message, result.updated ? "success" : "info");
      if (result.updated) refetch();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };
  const [sortBy, setSortBy] = useState<SortKey>("name");
  const [order, setOrder] = useState<Order>("asc");
  const [editFields, setEditFields] = useState<
    Record<number, { quantity?: string; storage_location?: string; expiration_date?: string }>
  >({});

  const handleSort = (key: SortKey) => {
    const newOrder = sortBy === key && order === "asc" ? "desc" : "asc";
    setSortBy(key);
    setOrder(newOrder);
    refetch(search, key, newOrder);
  };

  const handleSearch = (value: string) => {
    setSearch(value);
    refetch(value, sortBy, order);
  };

  const handleFieldChange = (id: number, field: string, value: string) => {
    setEditFields((prev) => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }));
  };

  const handleUpdate = async (id: number, barcode: string) => {
    const fields = editFields[id];
    if (!fields) return;

    try {
      const updateData: { quantity?: number; storage_location?: string; expiration_date?: string } = {};
      if (fields.quantity !== undefined) {
        const qty = parseInt(fields.quantity, 10);
        if (isNaN(qty) || qty < 0) return;
        if (qty === 0 && !window.confirm("Artikel wirklich löschen?")) return;
        updateData.quantity = qty;
      }
      if (fields.storage_location !== undefined) updateData.storage_location = fields.storage_location;
      if (fields.expiration_date !== undefined) updateData.expiration_date = fields.expiration_date;

      const result = await inventory.update(barcode, updateData);
      notify(result.message, "success");
      setEditFields((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Aktualisieren", "error");
    }
  };

  const handleDelete = async (barcode: string) => {
    if (!window.confirm("Artikel wirklich löschen?")) return;
    try {
      const result = await inventory.delete(barcode);
      notify(result.message, "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Löschen", "error");
    }
  };

  const columns: { key: SortKey; label: string }[] = [
    { key: "name", label: "Name" },
    { key: "barcode", label: "Barcode" },
    { key: "quantity", label: "Menge" },
    { key: "category", label: "Kategorie" },
    { key: "added_date", label: "Hinzugefügt" },
  ];

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Inventarverwaltung
      </Typography>
      <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
        <Button
          variant="outlined"
          size="small"
          startIcon={<FileDownloadIcon />}
          onClick={handleExport}
        >
          Export
        </Button>
        <Button
          variant="outlined"
          size="small"
          startIcon={<FileUploadIcon />}
          onClick={() => fileInputRef.current?.click()}
        >
          Import
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          hidden
          onChange={handleImport}
        />
        {items.some((i) => i.name === "Unbekanntes Produkt") && (
          <Button
            variant="outlined"
            size="small"
            color="warning"
            startIcon={<RefreshIcon />}
            onClick={handleRelookupAll}
          >
            Unbekannte nachschlagen
          </Button>
        )}
        {items.some((i) => !i.image_url) && (
          <Button
            variant="outlined"
            size="small"
            startIcon={<ImageSearchIcon />}
            onClick={handleBackfillImages}
          >
            Bilder nachschlagen
          </Button>
        )}
        {picnicStatus?.enabled && (
          <Button
            variant="outlined"
            size="small"
            startIcon={<LocalGroceryStoreIcon />}
            onClick={() => navigate("/picnic-import")}
          >
            Picnic-Bestellung importieren
          </Button>
        )}
      </Box>
      <TextField
        label="Suche nach Name oder Kategorie"
        variant="outlined"
        fullWidth
        margin="normal"
        value={search}
        onChange={(e) => handleSearch(e.target.value)}
      />
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              {columns.map((col) => (
                <TableCell key={col.key}>
                  <TableSortLabel
                    active={sortBy === col.key}
                    direction={sortBy === col.key ? order : "asc"}
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                  </TableSortLabel>
                </TableCell>
              ))}
              <TableCell>Lagerort</TableCell>
              <TableCell>Ablaufdatum</TableCell>
              <TableCell>Aktionen</TableCell>
              <TableCell>Nachbest.</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow
                key={item.id}
                sx={{
                  ...(item.quantity === 0 && {
                    backgroundColor: "action.hover",
                  }),
                }}
              >
                <TableCell>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    {item.image_url && (
                      <Box
                        component="img"
                        src={item.image_url}
                        alt=""
                        sx={{ width: 36, height: 36, objectFit: "contain", flexShrink: 0 }}
                      />
                    )}
                    <span>
                      {item.name}
                      {item.name === "Unbekanntes Produkt" && (
                        <IconButton size="small" onClick={() => handleRelookup(item.barcode)} title="Nochmal nachschlagen">
                          <RefreshIcon fontSize="small" />
                        </IconButton>
                      )}
                    </span>
                  </Box>
                </TableCell>
                <TableCell>{item.barcode}</TableCell>
                <TableCell>
                  <TextField
                    type="number"
                    size="small"
                    sx={{ width: 80 }}
                    value={editFields[item.id]?.quantity ?? item.quantity}
                    onChange={(e) => handleFieldChange(item.id, "quantity", e.target.value)}
                  />
                  {(barcodeToOrderQty[item.barcode] ?? 0) > 0 && (
                    <Chip
                      label={`${barcodeToOrderQty[item.barcode]} in Bestellung`}
                      size="small"
                      color="warning"
                      sx={{ mt: 0.5 }}
                    />
                  )}
                  {item.quantity === 0 && trackedByBarcode.has(item.barcode) && (
                    <Typography
                      variant="caption"
                      color={(barcodeToOrderQty[item.barcode] ?? 0) > 0 ? "warning.main" : "error"}
                      display="block"
                      sx={{ mt: 0.5 }}
                    >
                      {(barcodeToOrderQty[item.barcode] ?? 0) > 0 ? "in Bestellung" : "leer, nachbestellen"}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{item.category}</TableCell>
                <TableCell>{new Date(item.added_date).toLocaleDateString("de-DE")}</TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    sx={{ width: 130 }}
                    value={
                      editFields[item.id]?.storage_location ??
                      item.storage_location?.name ??
                      ""
                    }
                    onChange={(e) =>
                      handleFieldChange(item.id, "storage_location", e.target.value)
                    }
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    type="date"
                    size="small"
                    sx={{ width: 150 }}
                    slotProps={{ inputLabel: { shrink: true } }}
                    value={editFields[item.id]?.expiration_date ?? item.expiration_date ?? ""}
                    onChange={(e) =>
                      handleFieldChange(item.id, "expiration_date", e.target.value)
                    }
                  />
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Button
                    variant="contained"
                    size="small"
                    sx={{ mr: 1 }}
                    onClick={() => handleUpdate(item.id, item.barcode)}
                    disabled={!editFields[item.id]}
                  >
                    Speichern
                  </Button>

                  <Button
                    variant="outlined"
                    color="error"
                    size="small"
                    onClick={() => handleDelete(item.barcode)}
                  >
                    Löschen
                  </Button>
                </TableCell>
                <TableCell>
                  <InventoryRestockButton
                    tracked={trackedByBarcode.get(item.barcode)}
                    onClick={() =>
                      openTrackedForm(
                        item.barcode,
                        trackedByBarcode.get(item.barcode)
                      )
                    }
                  />
                </TableCell>
              </TableRow>
            ))}
            {!loading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  Keine Artikel gefunden.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TrackedProductForm
        open={trackedFormOpen}
        mode={trackedFormExisting ? "edit" : "create"}
        initialBarcode={trackedFormBarcode}
        existing={trackedFormExisting}
        onClose={() => setTrackedFormOpen(false)}
        onSubmitCreate={async (data) => {
          await trackedProducts.create(data);
          notify("Nachbestellungs-Regel angelegt", "success");
        }}
        onSubmitUpdate={async (barcode, data) => {
          await trackedProducts.update(barcode, data);
          notify("Nachbestellungs-Regel aktualisiert", "success");
        }}
      />
    </Paper>
  );
};

export default InventoryPage;
