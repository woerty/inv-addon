import { useCallback, useEffect, useState } from "react";
import {
  listTrackedProducts,
  createTrackedProduct,
  updateTrackedProduct,
  deleteTrackedProduct,
  resolveTrackedProductPreview,
  promoteTrackedProductBarcode,
} from "../api/client";
import type {
  TrackedProduct,
  TrackedProductCreate,
  TrackedProductUpdate,
  ResolvePreview,
  PromoteBarcodeResponse,
} from "../types";

export function useTrackedProducts() {
  const [items, setItems] = useState<TrackedProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listTrackedProducts());
    } catch (e) {
      // 503 when Picnic is disabled → render as empty state
      setItems([]);
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const create = async (data: TrackedProductCreate) => {
    const result = await createTrackedProduct(data);
    await refetch();
    return result;
  };

  const update = async (barcode: string, data: TrackedProductUpdate) => {
    const result = await updateTrackedProduct(barcode, data);
    await refetch();
    return result;
  };

  const remove = async (barcode: string) => {
    await deleteTrackedProduct(barcode);
    await refetch();
  };

  const promote = async (synthBarcode: string, newBarcode: string): Promise<PromoteBarcodeResponse> => {
    const result = await promoteTrackedProductBarcode(synthBarcode, newBarcode);
    await refetch();
    return result;
  };

  return { items, loading, error, refetch, create, update, remove, promote };
}

export function useResolvePreview() {
  const [preview, setPreview] = useState<ResolvePreview | null>(null);
  const [loading, setLoading] = useState(false);

  const resolve = useCallback(async (barcode: string) => {
    if (!barcode.trim()) {
      setPreview(null);
      return;
    }
    setLoading(true);
    try {
      setPreview(await resolveTrackedProductPreview(barcode));
    } catch {
      setPreview({
        resolved: false,
        picnic_id: null,
        picnic_name: null,
        picnic_image_id: null,
        picnic_unit_quantity: null,
        reason: "error",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => setPreview(null), []);

  return { preview, loading, resolve, clear };
}
