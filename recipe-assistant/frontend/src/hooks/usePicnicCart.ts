import { useCallback, useEffect, useState } from "react";
import { getCart, cartAdd, cartRemove, cartClear } from "../api/client";
import type { Cart } from "../types";

export function usePicnicCart() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCart();
      setCart(data);
    } catch {
      setCart(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  const add = useCallback(async (picnicId: string, count = 1) => {
    const updated = await cartAdd(picnicId, count);
    setCart(updated);
    return updated;
  }, []);

  const remove = useCallback(async (picnicId: string, count = 1) => {
    const updated = await cartRemove(picnicId, count);
    setCart(updated);
    return updated;
  }, []);

  const clear = useCallback(async () => {
    const updated = await cartClear();
    setCart(updated);
    return updated;
  }, []);

  return { cart, loading, refetch, add, remove, clear };
}
