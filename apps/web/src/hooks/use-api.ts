"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/** GET {path} on mount / when path changes. Keeps the previous data while reloading (no flicker when polling). */
export function useApi<T>(path: string | null) {
  const [nonce, setNonce] = useState(0);
  const key = path === null ? null : `${nonce}:${path}`;
  const [state, setState] = useState<{ key: string | null; data?: T; error?: unknown }>({ key: null });

  useEffect(() => {
    if (path === null) return;
    let alive = true;
    const k = `${nonce}:${path}`;
    api<T>(path).then(
      (data) => alive && setState({ key: k, data }),
      (error) => alive && setState((s) => ({ key: k, data: s.data, error })),
    );
    return () => {
      alive = false;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data, error: undefined })), []);
  return {
    data: state.data,
    error: state.key === key ? state.error : undefined,
    loading: key !== null && state.key !== key,
    reload,
    setData,
  };
}

/** Calls fn every ms while ms is not null. */
export function useInterval(fn: () => void, ms: number | null) {
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  });
  useEffect(() => {
    if (ms === null) return;
    const id = setInterval(() => ref.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}
