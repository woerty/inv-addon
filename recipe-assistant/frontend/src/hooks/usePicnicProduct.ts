import { useCallback, useState } from "react";
import { getProductDetail } from "../api/client";
import type { ProductDetail } from "../types";

export function usePicnicProduct() {
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (picnicId: string) => {
    setLoading(true);
    setProduct(null);
    try {
      const data = await getProductDetail(picnicId);
      setProduct(data);
    } catch {
      setProduct(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => setProduct(null), []);

  return { product, loading, load, clear };
}
