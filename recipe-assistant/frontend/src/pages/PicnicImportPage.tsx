import { useEffect, useState } from "react";
import { Alert, Box, Button, Paper, Typography } from "@mui/material";
import { usePicnicImport } from "../hooks/usePicnic";
import { getStorageLocations } from "../api/client";
import type { ImportDecision } from "../types";
import { ReviewCard } from "../components/picnic/ReviewCard";

export default function PicnicImportPage() {
  const { data, loading, error, fetchImport, commit } = usePicnicImport();
  const [decisions, setDecisions] = useState<Record<string, ImportDecision>>({});
  const [storageLocations, setStorageLocations] = useState<string[]>([]);

  useEffect(() => {
    getStorageLocations().then((locs) => setStorageLocations(locs.map((l) => l.name)));
  }, []);

  const handleDecision = (d: ImportDecision) => {
    setDecisions((prev) => ({ ...prev, [d.picnic_id]: d }));
  };

  const handleCommit = async (deliveryId: string) => {
    const delivery = data?.deliveries.find((d) => d.delivery_id === deliveryId);
    if (!delivery) return;
    const finalDecisions: ImportDecision[] = delivery.items.map(
      (item) =>
        decisions[item.picnic_id] ?? {
          picnic_id: item.picnic_id,
          action: "skip",
        }
    );
    const result = await commit(deliveryId, finalDecisions);
    alert(
      `Importiert: ${result.imported} zugeordnet, ${result.created} neu, ${result.skipped} übersprungen.`
    );
    await fetchImport();
  };

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Picnic-Bestellungen importieren
      </Typography>

      <Button variant="contained" onClick={fetchImport} disabled={loading}>
        {loading ? "Lade..." : "Lieferungen abrufen"}
      </Button>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      {data && data.deliveries.length === 0 && (
        <Typography color="text.secondary" sx={{ mt: 2 }}>
          Keine neuen Lieferungen.
        </Typography>
      )}

      {data?.deliveries.map((delivery) => (
        <Box key={delivery.delivery_id} sx={{ mt: 3 }}>
          <Typography variant="h6" gutterBottom>
            Lieferung {delivery.delivery_id} — {delivery.items.length} Artikel
          </Typography>
          {delivery.items.map((item) => (
            <ReviewCard
              key={item.picnic_id}
              candidate={item}
              storageLocations={storageLocations}
              onChange={handleDecision}
            />
          ))}
          <Button
            variant="contained"
            color="success"
            sx={{ mt: 2 }}
            onClick={() => handleCommit(delivery.delivery_id)}
          >
            Bestätigte importieren
          </Button>
        </Box>
      ))}
    </Paper>
  );
}
