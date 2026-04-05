import { useEffect, useState } from "react";
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
    <div className="p-4 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Picnic-Bestellungen importieren</h1>

      <button
        onClick={fetchImport}
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded"
      >
        {loading ? "Lade..." : "Lieferungen abrufen"}
      </button>

      {error && <div className="text-red-600 mt-2">{error}</div>}

      {data && data.deliveries.length === 0 && (
        <div className="mt-4 text-gray-600">Keine neuen Lieferungen.</div>
      )}

      {data?.deliveries.map((delivery) => (
        <div key={delivery.delivery_id} className="mt-6">
          <h2 className="text-lg font-semibold mb-2">
            Lieferung {delivery.delivery_id} — {delivery.items.length} Artikel
          </h2>
          <div className="space-y-3">
            {delivery.items.map((item) => (
              <ReviewCard
                key={item.picnic_id}
                candidate={item}
                storageLocations={storageLocations}
                onChange={handleDecision}
              />
            ))}
          </div>
          <button
            onClick={() => handleCommit(delivery.delivery_id)}
            className="mt-4 bg-green-600 text-white px-4 py-2 rounded"
          >
            Bestätigte importieren
          </button>
        </div>
      ))}
    </div>
  );
}
