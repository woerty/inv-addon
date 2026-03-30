import { useCallback, useEffect, useState } from "react";
import type { InventoryItem } from "../types";
import {
  getInventory,
  updateItem,
  deleteItem,
  addItemByBarcode,
  removeItemByBarcode,
} from "../api/client";

export function useInventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (search?: string, sortBy?: string, order?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getInventory(search, sortBy, order);
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Laden");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();

    // Refetch when page becomes visible (e.g. navigating back from scan page)
    const handleVisibility = () => {
      if (document.visibilityState === "visible") fetch();
    };
    const handleFocus = () => fetch();

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handleFocus);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleFocus);
    };
  }, [fetch]);

  const add = async (barcode: string, storageLocation?: string, expirationDate?: string) => {
    const result = await addItemByBarcode(barcode, storageLocation, expirationDate);
    await fetch();
    return result;
  };

  const remove = async (barcode: string) => {
    const result = await removeItemByBarcode(barcode);
    await fetch();
    return result;
  };

  const update = async (barcode: string, data: Parameters<typeof updateItem>[1]) => {
    const result = await updateItem(barcode, data);
    await fetch();
    return result;
  };

  const del = async (barcode: string) => {
    const result = await deleteItem(barcode);
    await fetch();
    return result;
  };

  return { items, loading, error, refetch: fetch, add, remove, update, delete: del };
}
