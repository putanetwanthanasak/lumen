/** Load data for a screen: loading, error (with retry) or ready. */
import { useCallback, useEffect, useState } from "react";

export type Load<T> =
  | { state: "loading" }
  | { state: "error"; error: unknown }
  | { state: "ready"; data: T };

export function useLoad<T>(load: () => Promise<T>): [Load<T>, () => void] {
  const [result, setResult] = useState<Load<T>>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setResult({ state: "loading" });
    load().then(
      (data) => live && setResult({ state: "ready", data }),
      (error: unknown) => live && setResult({ state: "error", error }),
    );
    return () => {
      live = false;
    };
    // `load` is a stable module function per screen; reload goes through `attempt`.
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return [result, reload];
}
