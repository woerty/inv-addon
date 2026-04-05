import { useCallback, useEffect, useState } from "react";
import {
  getPicnicStatus,
  fetchPicnicImport,
  commitPicnicImport,
  getShoppingList,
  addShoppingListItem,
  updateShoppingListItem,
  deleteShoppingListItem,
  syncShoppingListToCart,
  searchPicnic,
  startPicnicLogin,
  sendPicnicLoginCode,
  verifyPicnicLoginCode,
} from "../api/client";
import type {
  PicnicStatus,
  PicnicLoginChannel,
  ImportFetchResponse,
  ImportDecision,
  ShoppingListItem,
  PicnicSearchResult,
  CartSyncResponse,
} from "../types";

export function usePicnicStatus() {
  const [status, setStatus] = useState<PicnicStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(() => {
    setLoading(true);
    return getPicnicStatus()
      .then((s) => {
        setStatus(s);
        return s;
      })
      .catch(() => {
        const fallback: PicnicStatus = {
          enabled: false,
          needs_login: false,
          account: null,
        };
        setStatus(fallback);
        return fallback;
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { status, loading, refetch };
}

export type LoginPhase =
  | "idle"
  | "starting"
  | "awaiting_2fa"
  | "sending_code"
  | "awaiting_code"
  | "verifying"
  | "success";

export function usePicnicLogin() {
  const [phase, setPhase] = useState<LoginPhase>("idle");
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    setError(null);
    setPhase("starting");
    try {
      const r = await startPicnicLogin();
      setPhase(r.status === "ok" ? "success" : "awaiting_2fa");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Start");
      setPhase("idle");
    }
  }, []);

  const sendCode = useCallback(async (channel: PicnicLoginChannel) => {
    setError(null);
    setPhase("sending_code");
    try {
      await sendPicnicLoginCode(channel);
      setPhase("awaiting_code");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Senden des Codes");
      setPhase("awaiting_2fa");
    }
  }, []);

  const verify = useCallback(async (code: string) => {
    setError(null);
    setPhase("verifying");
    try {
      await verifyPicnicLoginCode(code);
      setPhase("success");
    } catch (e) {
      // Keep the user in awaiting_code so they can retry the code
      setError(e instanceof Error ? e.message : "Ungültiger Code");
      setPhase("awaiting_code");
    }
  }, []);

  const reset = useCallback(() => {
    setPhase("idle");
    setError(null);
  }, []);

  return { phase, error, start, sendCode, verify, reset };
}

export function usePicnicImport() {
  const [data, setData] = useState<ImportFetchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchImport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchPicnicImport();
      setData(response);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setLoading(false);
    }
  }, []);

  const commit = useCallback(
    async (delivery_id: string, decisions: ImportDecision[]) => {
      return commitPicnicImport(delivery_id, decisions);
    },
    []
  );

  return { data, loading, error, fetchImport, commit };
}

export function useShoppingList() {
  const [items, setItems] = useState<ShoppingListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await getShoppingList());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const add = async (data: Parameters<typeof addShoppingListItem>[0]) => {
    await addShoppingListItem(data);
    await refetch();
  };

  const update = async (id: number, data: Parameters<typeof updateShoppingListItem>[1]) => {
    await updateShoppingListItem(id, data);
    await refetch();
  };

  const remove = async (id: number) => {
    await deleteShoppingListItem(id);
    await refetch();
  };

  const sync = async (): Promise<CartSyncResponse> => {
    const result = await syncShoppingListToCart();
    await refetch();
    return result;
  };

  return { items, loading, refetch, add, update, remove, sync };
}

export function usePicnicSearch() {
  const [results, setResults] = useState<PicnicSearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const response = await searchPicnic(q);
      setResults(response.results);
    } finally {
      setLoading(false);
    }
  }, []);

  return { results, loading, search };
}
