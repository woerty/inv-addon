import { useCallback, useEffect, useRef, useState } from "react";
import type { InventoryItem } from "../types";
import {
  getInventory,
  updateItem,
  deleteItem,
  addItemByBarcode,
  removeItemByBarcode,
  createCustomProduct,
} from "../api/client";

// focus + visibilitychange usually fire together; one fetch is enough.
const REFETCH_COALESCE_MS = 2000;

const sameItem = (a: InventoryItem, b: InventoryItem) =>
  a.id === b.id &&
  a.barcode === b.barcode &&
  a.name === b.name &&
  a.quantity === b.quantity &&
  a.category === b.category &&
  a.storage_location?.id === b.storage_location?.id &&
  a.storage_location?.name === b.storage_location?.name &&
  a.expiration_date === b.expiration_date &&
  a.image_url === b.image_url &&
  a.include_in_sheet === b.include_in_sheet &&
  a.added_date === b.added_date &&
  a.updated_date === b.updated_date;

/** Reuse the previous object for every unchanged item so memoized rows skip
 *  re-rendering after a refetch; keep the old array if nothing changed. */
function reconcile(prev: InventoryItem[], next: InventoryItem[]): InventoryItem[] {
  const prevById = new Map(prev.map((i) => [i.id, i]));
  let changed = prev.length !== next.length;
  const merged = next.map((item, idx) => {
    const old = prevById.get(item.id);
    if (old && sameItem(old, item)) {
      if (prev[idx] !== old) changed = true;
      return old;
    }
    changed = true;
    return item;
  });
  return changed ? merged : prev;
}

export function useInventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastFetchRef = useRef(0);

  const fetch = useCallback(async () => {
    lastFetchRef.current = Date.now();
    setLoading(true);
    setError(null);
    try {
      const data = await getInventory();
      setItems((prev) => reconcile(prev, data));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Laden");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();

    // Refetch when the page comes back into view (other tab, HA panel switch).
    const refetchIfStale = () => {
      if (Date.now() - lastFetchRef.current > REFETCH_COALESCE_MS) fetch();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") refetchIfStale();
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", refetchIfStale);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", refetchIfStale);
    };
  }, [fetch]);

  const add = useCallback(async (barcode: string, storageLocation?: string, expirationDate?: string) => {
    const result = await addItemByBarcode(barcode, storageLocation, expirationDate);
    await fetch();
    return result;
  }, [fetch]);

  const remove = useCallback(async (barcode: string) => {
    const result = await removeItemByBarcode(barcode);
    await fetch();
    return result;
  }, [fetch]);

  const update = useCallback(async (barcode: string, data: Parameters<typeof updateItem>[1]) => {
    const result = await updateItem(barcode, data);
    await fetch();
    return result;
  }, [fetch]);

  const del = useCallback(async (barcode: string) => {
    const result = await deleteItem(barcode);
    await fetch();
    return result;
  }, [fetch]);

  const createCustom = useCallback(async (data: Parameters<typeof createCustomProduct>[0]) => {
    const result = await createCustomProduct(data);
    await fetch();
    return result;
  }, [fetch]);

  return { items, loading, error, refetch: fetch, add, remove, update, delete: del, createCustom };
}
