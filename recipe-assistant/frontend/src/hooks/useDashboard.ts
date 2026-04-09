import { useCallback, useEffect, useState } from "react";
import type { DashboardSummary, DashboardProductDetail } from "../types";
import { getDashboardSummary, getDashboardProductDetail, togglePin as apiTogglePin } from "../api/client";

export function useDashboard(days: number = 30) {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getDashboardSummary(days);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Laden");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetch();
    const handleVisibility = () => {
      if (document.visibilityState === "visible") fetch();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [fetch]);

  const togglePin = async (barcode: string) => {
    await apiTogglePin(barcode);
    await fetch();
  };

  return { data, loading, error, refetch: fetch, togglePin };
}

export function useProductDetail() {
  const [data, setData] = useState<DashboardProductDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (barcode: string, days: number = 30) => {
    setLoading(true);
    try {
      const result = await getDashboardProductDetail(barcode, days);
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const close = () => setData(null);

  return { data, loading, fetch, close };
}
