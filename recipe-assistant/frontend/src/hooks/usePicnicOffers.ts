import { useCallback, useEffect, useState } from "react";
import { getOffers } from "../api/client";
import type { OfferItem } from "../types";

export function usePicnicOffers() {
  const [offers, setOffers] = useState<OfferItem[]>([]);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getOffers();
      setOffers(result.offers);
    } catch {
      setOffers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  return { offers, loading, refetch };
}
