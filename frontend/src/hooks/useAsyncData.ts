import { useState, useEffect } from "react";

export interface AsyncDataState<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | null;
}

export function useAsyncData<T>(
  fetcher: (isCancelled: () => boolean) => Promise<T>,
  deps: readonly unknown[],
): AsyncDataState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

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
  }, deps);

  return { data, loading, error };
}
