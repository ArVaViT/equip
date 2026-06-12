import { useState, useEffect, useCallback } from "react";

export interface AsyncDataState<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | null;
  /**
   * Re-runs the fetcher (e.g. after a mutation). Cancellation semantics
   * match the deps-change path: an in-flight fetch from the previous run
   * is marked cancelled and its result discarded.
   */
  refetch: () => void;
}

export function useAsyncData<T>(
  fetcher: (isCancelled: () => boolean) => Promise<T>,
  deps: readonly unknown[],
): AsyncDataState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  // Internal reload key: bumping it re-fires the effect without callers
  // having to thread their own reloadKey through deps (the hand-rolled
  // pattern this hook exists to replace).
  const [reloadKey, setReloadKey] = useState(0);

  const refetch = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let cancelled = false;
    const isCancelled = () => cancelled;

    setLoading(true);
    setError(null);

    fetcher(isCancelled)
      .then((result) => {
        if (!cancelled) {
          setData(result);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadKey]);

  return { data, loading, error, refetch };
}
