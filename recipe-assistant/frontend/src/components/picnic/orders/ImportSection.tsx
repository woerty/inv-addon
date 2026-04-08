import { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Paper, Typography } from "@mui/material";
import { usePicnicImport } from "../../../hooks/usePicnic";
import { useTrackedProducts } from "../../../hooks/useTrackedProducts";
import { getStorageLocations } from "../../../api/client";
import { useNotification } from "../../NotificationProvider";
import { ReviewCard } from "../ReviewCard";
import PromoteBarcodeDialog from "../PromoteBarcodeDialog";
import type { ImportDecision, TrackedProduct } from "../../../types";

export default function ImportSection() {
  const { data, loading, error, fetchImport, commit } = usePicnicImport();
  const { items: tracked, promote } = useTrackedProducts();
  const { notify } = useNotification();
  const [storageLocations, setStorageLocations] = useState<string[]>([]);
  const [decisions, setDecisions] = useState<Record<string, Record<string, ImportDecision>>>({});
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);

  useEffect(() => {
    fetchImport();
    getStorageLocations().then((locs) => setStorageLocations(locs.map((l) => l.name))).catch(() => {});
  }, [fetchImport]);

  const synthTrackedMap = useMemo(() => {
    const map: Record<string, TrackedProduct> = {};
    for (const tp of tracked) {
      if (tp.barcode.startsWith("picnic:") && tp.picnic_id) {
        map[tp.picnic_id] = tp;
      }
    }
    return map;
  }, [tracked]);

  const handleDecision = (deliveryId: string, decision: ImportDecision) => {
    setDecisions(prev => ({
      ...prev,
      [deliveryId]: { ...prev[deliveryId], [decision.picnic_id]: decision },
    }));
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

  const handleCommit = async (deliveryId: string) => {
    const deliveryDecisions = Object.values(decisions[deliveryId] ?? {});
    if (deliveryDecisions.length === 0) return;
    try {
      const result = await commit(deliveryId, deliveryDecisions);
      notify(`Import: ${result.imported} zugeordnet, ${result.created} neu, ${result.skipped} übersprungen`, "success");
      fetchImport();
    } catch {
      notify("Import fehlgeschlagen", "error");
    }
  };

  if (loading) return <Typography color="text.secondary">Lade Lieferungen...</Typography>;
  if (error) return <Alert severity="error">{error}</Alert>;
  if (!data || data.deliveries.length === 0) {
    return <Typography color="text.secondary" textAlign="center" py={2}>Keine neuen Lieferungen zum Importieren</Typography>;
  }

  return (
    <Box>
      {data.deliveries.map(delivery => (
        <Paper key={delivery.delivery_id} variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" fontWeight={500} gutterBottom>
            Lieferung vom {delivery.delivered_at ? new Date(delivery.delivered_at).toLocaleDateString("de-DE") : "Unbekannt"}
          </Typography>
          {delivery.items.map(candidate => (
            <ReviewCard
              key={candidate.picnic_id}
              candidate={candidate}
              storageLocations={storageLocations}
              onChange={d => handleDecision(delivery.delivery_id, d)}
              synthTracked={synthTrackedMap[candidate.picnic_id] ?? null}
              onPromote={setPromoteTarget}
            />
          ))}
          <Button variant="contained"
            onClick={() => handleCommit(delivery.delivery_id)}
            disabled={Object.keys(decisions[delivery.delivery_id] ?? {}).length === 0}
            sx={{ mt: 1 }}>
            Importieren
          </Button>
        </Paper>
      ))}
      <PromoteBarcodeDialog
        tracked={promoteTarget}
        onClose={() => setPromoteTarget(null)}
        onPromote={handlePromote}
      />
    </Box>
  );
}
