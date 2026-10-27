/** Hash routing without a package: "#/home", "#/think", ... (DESIGN.md section 6). */
import { useSyncExternalStore } from "react";

export const ROUTES = ["settings", "home", "think", "result", "months", "buffer", "alerts"] as const;
export type Route = (typeof ROUTES)[number];

function current(): Route | null {
  const name = window.location.hash.replace(/^#\/?/, "");
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : null;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** The route in the address bar, or null when there is none (the app decides). */
export function useRoute(): Route | null {
  return useSyncExternalStore(subscribe, current);
}

export function navigate(route: Route): void {
  window.location.hash = `#/${route}`;
}
