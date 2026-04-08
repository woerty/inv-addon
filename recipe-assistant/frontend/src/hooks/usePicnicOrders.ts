import { useCallback, useEffect, useState } from "react";
import { getPendingOrders } from "../api/client";
import type { PendingOrdersResponse } from "../types";

export function usePicnicPendingOrders() {
  const [data, setData] = useState<PendingOrdersResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getPendingOrders();
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  const quantityMap = data?.quantity_map ?? {};

  return { orders: data?.orders ?? [], quantityMap, loading, refetch };
}
