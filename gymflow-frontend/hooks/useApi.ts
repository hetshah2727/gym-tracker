"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, withQuery } from "@/services/api";

type Query = Record<string, string | number | boolean | null | undefined>;

/** Minimal data-fetching hook: GET `path` (null = skip) and expose reload(). */
export function useApi<T>(path: string | null, query?: Query) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const key = path ? withQuery(path, query) : null;
  const latest = useRef(key);
  latest.current = key;

  const load = useCallback(async () => {
    if (!key) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api<T>(key);
      if (latest.current === key) setData(result);
    } catch (e) {
      if (latest.current === key) setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      if (latest.current === key) setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}
