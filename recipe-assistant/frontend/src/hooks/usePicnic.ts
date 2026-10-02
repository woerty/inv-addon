import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  getPicnicStatus,
  fetchPicnicImport,
  commitPicnicImport,
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
  PicnicSearchResult,
} from "../types";

// /picnic/status is a live round-trip to Picnic. Share one result between the
// navbar and every page instead of re-asking on each mount; revalidate in the
// background once it is older than STATUS_MAX_AGE_MS.
const STATUS_MAX_AGE_MS = 60_000;
let statusCache: PicnicStatus | null = null;
let statusFetchedAt = 0;
let statusInflight: Promise<PicnicStatus> | null = null;
const statusListeners = new Set<() => void>();

function loadPicnicStatus(force = false): Promise<PicnicStatus> {
  if (statusInflight && !force) return statusInflight;
  const request = getPicnicStatus()
    .catch((): PicnicStatus => ({ enabled: false, needs_login: false, account: null }))
    .then((s) => {
      statusCache = s;
      statusFetchedAt = Date.now();
      if (statusInflight === request) statusInflight = null;
      statusListeners.forEach((l) => l());
      return s;
    });
  statusInflight = request;
  return request;
}

const subscribeStatus = (listener: () => void) => {
  statusListeners.add(listener);
  return () => {
    statusListeners.delete(listener);
  };
};

export function usePicnicStatus() {
  const status = useSyncExternalStore(subscribeStatus, () => statusCache);

  useEffect(() => {
    if (Date.now() - statusFetchedAt > STATUS_MAX_AGE_MS) loadPicnicStatus();
  }, []);

  const refetch = useCallback(() => loadPicnicStatus(true), []);

  return { status, loading: status === null, refetch };
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
