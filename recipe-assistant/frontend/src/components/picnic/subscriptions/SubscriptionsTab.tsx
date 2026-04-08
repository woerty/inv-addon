import { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { useTrackedProducts } from "../../../hooks/useTrackedProducts";
import { useNotification } from "../../NotificationProvider";
import SubscriptionCard from "./SubscriptionCard";
import TrackedProductForm from "../../tracked/TrackedProductForm";
import PromoteBarcodeDialog from "../PromoteBarcodeDialog";
import type { TrackedProduct, TrackedProductCreate, TrackedProductUpdate } from "../../../types";

interface SubscriptionsTabProps {
  orderQuantities: Record<string, number>;
}

export default function SubscriptionsTab({ orderQuantities }: SubscriptionsTabProps) {
  const { items, loading, create, update, remove, promote, refetch } = useTrackedProducts();
  const { notify } = useNotification();
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TrackedProduct | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);

  const handleCreate = async (data: TrackedProductCreate) => {
    await create(data);
    notify("Abo erstellt", "success");
  };

  const handleUpdate = async (barcode: string, data: TrackedProductUpdate) => {
    await update(barcode, data);
    notify("Abo aktualisiert", "success");
  };

  const handleDelete = async (item: TrackedProduct) => {
    if (!window.confirm(`"${item.picnic_name || item.name}" wirklich löschen?`)) return;
    await remove(item.barcode);
    notify("Abo gelöscht", "success");
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditTarget(null);
  };

  if (loading) {
    return <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>;
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h6">Abos ({items.length})</Typography>
        <Button startIcon={<AddIcon />} variant="contained" size="small" onClick={() => setFormOpen(true)}>
          Neues Abo
        </Button>
      </Box>
      {items.length === 0 ? (
        <Typography color="text.secondary" textAlign="center" py={4}>
          Noch keine Abos eingerichtet
        </Typography>
      ) : (
        items.map(item => (
          <SubscriptionCard
            key={item.barcode}
            item={item}
            onOrder={orderQuantities[item.picnic_id] ?? 0}
            onEdit={setEditTarget}
            onDelete={handleDelete}
          />
        ))
      )}
      <TrackedProductForm
        open={formOpen || editTarget !== null}
        mode={editTarget ? "edit" : "create"}
        existing={editTarget ?? undefined}
        onClose={handleFormClose}
        onSubmitCreate={handleCreate}
        onSubmitUpdate={handleUpdate}
      />
      {promoteTarget && (
        <PromoteBarcodeDialog
          tracked={promoteTarget}
          onClose={() => setPromoteTarget(null)}
          onPromote={async (synthBarcode, newBarcode) => {
            const result = await promote(synthBarcode, newBarcode);
            refetch();
            return result;
          }}
        />
      )}
    </Box>
  );
}
