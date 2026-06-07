import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

type RefreshFn = () => Promise<unknown> | unknown;

interface RefreshContextValue {
  /** Register a refetch fn; returns an unregister fn. */
  register: (fn: RefreshFn) => () => void;
  /** Run all currently-registered refetch fns in parallel. */
  refreshAll: () => Promise<void>;
  /** True while refreshAll is in flight. */
  refreshing: boolean;
  /** True when at least one refetch fn is registered. */
  canRefresh: boolean;
}

const RefreshContext = createContext<RefreshContextValue | null>(null);

export function RefreshProvider({ children }: { children: ReactNode }) {
  const fnsRef = useRef<Set<RefreshFn>>(new Set());
  const [refreshing, setRefreshing] = useState(false);
  const [canRefresh, setCanRefresh] = useState(false);

  const register = useCallback((fn: RefreshFn) => {
    fnsRef.current.add(fn);
    setCanRefresh(fnsRef.current.size > 0);
    return () => {
      fnsRef.current.delete(fn);
      setCanRefresh(fnsRef.current.size > 0);
    };
  }, []);

  const refreshAll = useCallback(async () => {
    const fns = Array.from(fnsRef.current);
    if (fns.length === 0) return;
    setRefreshing(true);
    try {
      // Settled, not all: one failing refetch must not block the others.
      await Promise.allSettled(fns.map((fn) => Promise.resolve().then(fn)));
    } finally {
      setRefreshing(false);
    }
  }, []);

  return (
    <RefreshContext.Provider value={{ register, refreshAll, refreshing, canRefresh }}>
      {children}
    </RefreshContext.Provider>
  );
}

export function useRefresh(): RefreshContextValue {
  const ctx = useContext(RefreshContext);
  if (!ctx) throw new Error("useRefresh must be used within a RefreshProvider");
  return ctx;
}

/**
 * Register a refetch fn for the lifetime of the calling component.
 * Wrap `fn` in useCallback so the registration is stable across renders.
 */
export function useRegisterRefresh(fn: RefreshFn): void {
  const { register } = useRefresh();
  useEffect(() => register(fn), [register, fn]);
}
