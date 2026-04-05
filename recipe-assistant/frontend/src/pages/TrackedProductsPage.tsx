import { useState } from "react";
import { Alert, Box, Button, Container, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import { usePicnicStatus } from "../hooks/usePicnic";
import { useNotification } from "../components/NotificationProvider";
import TrackedProductCard from "../components/tracked/TrackedProductCard";
import TrackedProductForm from "../components/tracked/TrackedProductForm";
import PromoteBarcodeDialog from "../components/picnic/PromoteBarcodeDialog";
import type { TrackedProduct } from "../types";

const TrackedProductsPage = () => {
  const { status: picnicStatus, loading: statusLoading } = usePicnicStatus();
  const { items, loading, error, create, update, remove, promote } = useTrackedProducts();
  const { notify } = useNotification();

  const [formOpen, setFormOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<TrackedProduct | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);

  if (statusLoading) return null;
  if (!picnicStatus?.enabled) {
    return (
      <Container sx={{ mt: 4 }}>
        <Alert severity="info">
          Nachbestellungen benötigen die Picnic-Integration. Bitte zuerst
          Picnic einrichten.
        </Alert>
      </Container>
    );
  }

  const handleCreate = () => {
    setEditingItem(null);
    setFormOpen(true);
  };

  const handleEdit = (item: TrackedProduct) => {
    setEditingItem(item);
    setFormOpen(true);
  };

  const handlePromote = async (synthBarcode: string, newBarcode: string) => {
    const result = await promote(synthBarcode, newBarcode);
    notify(
      result.merged
        ? "Barcode übernommen (bestehende Regel ersetzt)"
        : "Barcode übernommen",
      "success"
    );
    return result;
  };

  const handleDelete = async (item: TrackedProduct) => {
    if (!window.confirm(`Regel für "${item.name}" wirklich entfernen?`)) return;
    try {
      await remove(item.barcode);
      notify("Regel entfernt", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  return (
    <Container sx={{ mt: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h4">Nachbestellungen</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleCreate}
        >
          Neu
        </Button>
      </Box>

      {loading && <Typography>Lädt…</Typography>}
      {error && !loading && <Alert severity="error">{error}</Alert>}
      {!loading && items.length === 0 && (
        <Typography color="text.secondary">
          Noch keine Nachbestellungs-Regeln angelegt.
        </Typography>
      )}

      {items.map((item) => (
        <TrackedProductCard
          key={item.barcode}
          item={item}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onPromote={setPromoteTarget}
        />
      ))}

      <PromoteBarcodeDialog
        tracked={promoteTarget}
        onClose={() => setPromoteTarget(null)}
        onPromote={handlePromote}
      />

      <TrackedProductForm
        open={formOpen}
        mode={editingItem ? "edit" : "create"}
        existing={editingItem ?? undefined}
        onClose={() => setFormOpen(false)}
        onSubmitCreate={async (data) => {
          await create(data);
          notify("Regel angelegt", "success");
        }}
        onSubmitUpdate={async (barcode, data) => {
          await update(barcode, data);
          notify("Regel aktualisiert", "success");
        }}
      />
    </Container>
  );
};

export default TrackedProductsPage;
