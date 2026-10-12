import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { DEFAULT_CASH, DEFAULT_SPEC } from "./spec";

export interface StrategyRunState {
  result: any | null;
  loading: boolean;
  error: string | null;
  progress: { stage: string; pct: number } | null;
  run: (spec?: any, cash?: number) => Promise<void>;
}

export function useStrategyRun(): StrategyRunState {
  const [result, setResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ stage: string; pct: number } | null>(null);
  const started = useRef(false);

  const run = useCallback(async (spec: any = DEFAULT_SPEC, cash: number = DEFAULT_CASH) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.strategyRun(spec, { initial_cash: cash, persist: false });
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    run();
  }, [run]);

  return { result, loading, error, progress, run };
}
