import { useCallback, useDeferredValue, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import PrintIcon from "@mui/icons-material/Print";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import { useInventory } from "../hooks/useInventory";
import { useNotification } from "../components/NotificationProvider";
import { useRegisterRefresh } from "../components/RefreshProvider";
import { exportData, importData, relookupBarcode, relookupAllUnknown, backfillImages, barcodeSheetUrl } from "../api/client";
import { usePicnicStatus } from "../hooks/usePicnic";
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import InventoryRow, { type InventoryUpdate } from "../components/inventory/InventoryRow";
import TrackedProductForm from "../components/tracked/TrackedProductForm";
import type { InventoryItem, TrackedProduct } from "../types";

type SortKey = "name" | "quantity" | "category" | "barcode" | "added_date";
type Order = "asc" | "desc";

const collator = new Intl.Collator("de", { sensitivity: "base", numeric: true });

const compareBy = (key: SortKey) => (a: InventoryItem, b: InventoryItem): number => {
  if (key === "quantity") return a.quantity - b.quantity;
  return collator.compare(a[key] ?? "", b[key] ?? "");
};

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "barcode", label: "Barcode" },
  { key: "quantity", label: "Menge" },
  { key: "category", label: "Kategorie" },
  { key: "added_date", label: "Hinzugefügt" },
];

const InventoryPage = () => {
  const inventory = useInventory();
  const { items, loading, refetch, update: updateItem, delete: deleteItem } = inventory;
  const { notify } = useNotification();
  const { status: picnicStatus } = usePicnicStatus();
  const navigate = useNavigate();

  const trackedProducts = useTrackedProducts();
  // A rule covers every EAN of its Picnic product, not just its own barcode.
  const trackedByBarcode = useMemo(() => {
    const map = new Map<string, TrackedProduct>();
    for (const tp of trackedProducts.items) {
      for (const barcode of [tp.barcode, ...tp.inventory_barcodes]) map.set(barcode, tp);
    }
    return map;
  }, [trackedProducts.items]);

  const { quantityMap: orderQuantities } = usePicnicPendingOrders();
  const barcodeToOrderQty = useMemo(() => {
    const map: Record<string, number> = {};
    for (const tp of trackedProducts.items) {
      const qty = orderQuantities[tp.picnic_id];
      if (tp.picnic_id && qty) {
        for (const barcode of [tp.barcode, ...tp.inventory_barcodes]) map[barcode] = qty;
      }
    }
    return map;
  }, [trackedProducts.items, orderQuantities]);

  const [trackedFormOpen, setTrackedFormOpen] = useState(false);
  const [trackedFormBarcode, setTrackedFormBarcode] = useState("");
  const [trackedFormExisting, setTrackedFormExisting] = useState<
    TrackedProduct | undefined
  >(undefined);

  const [customOpen, setCustomOpen] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [customLocation, setCustomLocation] = useState("");

  const handleCreateCustom = async () => {
    if (!customName.trim()) return;
    try {
      await inventory.createCustom({
        name: customName.trim(),
        category: customCategory.trim() || undefined,
        storage_location: customLocation.trim() || undefined,
      });
      notify(`Eigenes Produkt "${customName.trim()}" angelegt`, "success");
      setCustomOpen(false);
      setCustomName("");
      setCustomCategory("");
      setCustomLocation("");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Anlegen", "error");
    }
  };

  const handleToggleSheet = useCallback(async (barcode: string, value: boolean) => {
    try {
      await updateItem(barcode, { include_in_sheet: value });
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  }, [updateItem, notify]);

  const openTrackedForm = useCallback((barcode: string, existing?: TrackedProduct) => {
    setTrackedFormBarcode(barcode);
    setTrackedFormExisting(existing);
    setTrackedFormOpen(true);
  }, []);

  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleRelookup = useCallback(async (barcode: string) => {
    try {
      const result = await relookupBarcode(barcode);
      notify(result.message, result.updated ? "success" : "info");
      if (result.updated) refetch();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  }, [refetch, notify]);

  useRegisterRefresh(refetch);

  // Search and sort run client-side over the full list: no request per
  // keystroke, and a refetch can never drop the active filter.
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("name");
  const [order, setOrder] = useState<Order>("asc");
  const deferredSearch = useDeferredValue(search);

  const visibleItems = useMemo(() => {
    const needle = deferredSearch.trim().toLocaleLowerCase("de");
    const filtered = needle
      ? items.filter(
          (i) =>
            i.name.toLocaleLowerCase("de").includes(needle) ||
            (i.category ?? "").toLocaleLowerCase("de").includes(needle),
        )
      : [...items];
    const cmp = compareBy(sortBy);
    const dir = order === "asc" ? 1 : -1;
    return filtered.sort((a, b) => dir * cmp(a, b) || a.id - b.id);
  }, [items, deferredSearch, sortBy, order]);

  const handleSort = (key: SortKey) => {
    setOrder(sortBy === key && order === "asc" ? "desc" : "asc");
    setSortBy(key);
  };

  const handleSave = useCallback(async (barcode: string, data: InventoryUpdate) => {
    try {
      const result = await updateItem(barcode, data);
      notify(result.message, "success");
      return true;
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Aktualisieren", "error");
      return false;
    }
  }, [updateItem, notify]);

  const handleDelete = useCallback(async (barcode: string) => {
    if (!window.confirm("Artikel wirklich löschen?")) return;
    try {
      const result = await deleteItem(barcode);
      notify(result.message, "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Löschen", "error");
    }
  }, [deleteItem, notify]);

  return (
    <Paper variant="outlined" sx={{ p: 3, m: { xs: 1, md: 2 }, borderRadius: 3 }}>
      <Typography variant="h4" gutterBottom>
        Inventarverwaltung
      </Typography>
      <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap" }}>
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
        <Button
          variant="outlined"
          size="small"
          startIcon={<AddCircleOutlineIcon />}
          onClick={() => setCustomOpen(true)}
        >
          Eigenes Produkt anlegen
        </Button>
        <Button
          variant="outlined"
          size="small"
          startIcon={<PrintIcon />}
          component="a"
          href={barcodeSheetUrl()}
          target="_blank"
          rel="noopener"
        >
          Barcode-Blatt herunterladen
        </Button>
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
            onClick={() => navigate("/picnic", { state: { tab: "orders" } })}
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
        onChange={(e) => setSearch(e.target.value)}
      />
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              {COLUMNS.map((col) => (
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
              <TableCell>Auf PDF</TableCell>
              <TableCell>Aktionen</TableCell>
              <TableCell>Nachbest.</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleItems.map((item) => (
              <InventoryRow
                key={item.id}
                item={item}
                tracked={trackedByBarcode.get(item.barcode)}
                orderQty={barcodeToOrderQty[item.barcode] ?? 0}
                onSave={handleSave}
                onDelete={handleDelete}
                onToggleSheet={handleToggleSheet}
                onRelookup={handleRelookup}
                onOpenTracked={openTrackedForm}
              />
            ))}
            {!loading && visibleItems.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} align="center">
                  Keine Artikel gefunden.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Dialog open={customOpen} onClose={() => setCustomOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Eigenes Produkt anlegen</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            label="Name"
            fullWidth
            margin="normal"
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
          />
          <TextField
            label="Kategorie (optional)"
            fullWidth
            margin="normal"
            value={customCategory}
            onChange={(e) => setCustomCategory(e.target.value)}
          />
          <TextField
            label="Lagerort (optional)"
            fullWidth
            margin="normal"
            value={customLocation}
            onChange={(e) => setCustomLocation(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCustomOpen(false)}>Abbrechen</Button>
          <Button variant="contained" onClick={handleCreateCustom} disabled={!customName.trim()}>
            Anlegen
          </Button>
        </DialogActions>
      </Dialog>
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
