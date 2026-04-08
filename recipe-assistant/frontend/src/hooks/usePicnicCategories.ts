import { useCallback, useEffect, useState } from "react";
import { getCategories } from "../api/client";
import type { PicnicCategory } from "../types";

export function usePicnicCategories() {
  const [categories, setCategories] = useState<PicnicCategory[]>([]);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCategories();
      setCategories(data.categories);
    } catch {
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  return { categories, loading, refetch };
}
