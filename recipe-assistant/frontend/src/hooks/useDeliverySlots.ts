import { useCallback, useEffect, useState } from "react";
import { getDeliverySlots, setDeliverySlot } from "../api/client";
import type { DeliverySlot } from "../types";

export function useDeliverySlots(enabled: boolean) {
  const [slots, setSlots] = useState<DeliverySlot[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [cartTotalCents, setCartTotalCents] = useState(0);
  const [loading, setLoading] = useState(false);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getDeliverySlots();
      setSlots(data.slots);
      setSelectedSlotId(data.selected_slot_id);
      setCartTotalCents(data.cart_total_price_cents);
    } catch {
      setSlots([]);
      setSelectedSlotId(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) refetch();
  }, [enabled, refetch]);

  const select = useCallback(async (slotId: string) => {
    await setDeliverySlot(slotId);
    setSelectedSlotId(slotId);
    await refetch();
  }, [refetch]);

  return { slots, selectedSlotId, cartTotalCents, loading, refetch, select };
}
