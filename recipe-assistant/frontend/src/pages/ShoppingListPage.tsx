import { useState } from "react";
import { useShoppingList, usePicnicSearch } from "../hooks/usePicnic";
import type { CartSyncResponse } from "../types";

export default function ShoppingListPage() {
  const { items, remove, update, sync, add } = useShoppingList();
  const { results, search } = usePicnicSearch();
  const [searchQuery, setSearchQuery] = useState("");
  const [syncResult, setSyncResult] = useState<CartSyncResponse | null>(null);

  const statusColor = (status: string) =>
    status === "mapped" ? "text-green-600" : "text-red-600";

  const handleSync = async () => {
    const result = await sync();
    setSyncResult(result);
  };

  const handleAddFromSearch = async (picnic_id: string, name: string) => {
    await add({ picnic_id, name, quantity: 1 });
    setSearchQuery("");
    search("");
  };

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Einkaufsliste</h1>

      <div className="border rounded p-3 mb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); search(e.target.value); }}
            placeholder="Picnic-Produkt suchen..."
            className="flex-1 border rounded px-2 py-1"
          />
        </div>
        {results.length > 0 && (
          <ul className="mt-2 max-h-60 overflow-y-auto">
            {results.map((r) => (
              <li key={r.picnic_id}>
                <button
                  onClick={() => handleAddFromSearch(r.picnic_id, r.name)}
                  className="w-full text-left px-2 py-1 hover:bg-gray-100"
                >
                  {r.name} <span className="text-sm text-gray-500">{r.unit_quantity}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2 border rounded p-2">
            <span className={`font-bold ${statusColor(item.picnic_status)}`} title={item.picnic_status === "mapped" ? "bei Picnic verfügbar" : "nicht bei Picnic verfügbar"}>●</span>
            <div className="flex-1">
              <div>{item.name}</div>
              {item.picnic_status === "mapped" && item.picnic_name && item.picnic_name !== item.name && (
                <div className="text-xs text-gray-500">→ {item.picnic_name}</div>
              )}
              {item.picnic_status === "unavailable" && (
                <div className="text-xs text-red-500">nicht bei Picnic verfügbar</div>
              )}
            </div>
            <input
              type="number"
              min={1}
              value={item.quantity}
              onChange={(e) => update(item.id, { quantity: Number(e.target.value) })}
              className="w-16 border rounded px-1 py-0.5"
            />
            <button
              onClick={() => remove(item.id)}
              className="text-red-600 px-2"
            >
              ×
            </button>
          </li>
        ))}
      </ul>

      {items.length > 0 && (
        <button
          onClick={handleSync}
          className="mt-4 bg-green-600 text-white px-4 py-2 rounded"
        >
          In Picnic-Cart übertragen
        </button>
      )}

      {syncResult && (
        <div className="mt-4 border rounded p-3">
          <div>Hinzugefügt: {syncResult.added_count}</div>
          <div>Übersprungen (nicht bei Picnic verfügbar): {syncResult.skipped_count}</div>
          <div>Fehlgeschlagen: {syncResult.failed_count}</div>
          {syncResult.failed_count > 0 && (
            <ul className="mt-2 text-sm text-red-600">
              {syncResult.results
                .filter((r) => r.status === "failed")
                .map((r) => (
                  <li key={r.shopping_list_id}>
                    Item #{r.shopping_list_id}: {r.failure_reason}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
