import { useSyncExternalStore } from "react";

/**
 * A minimal hash router: `#/routes/60-4` and nothing more.
 *
 * Hash URLs need no server-side fallback, so the backend can serve the app as plain
 * static files, and every screen still has a link that can be shared.
 */
function subscribe(listener: () => void): () => void {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
}

function currentPath(): string {
  const hash = window.location.hash.replace(/^#/, "");
  return hash.startsWith("/") ? hash : "/";
}

/** The path split into decoded segments: "#/routes/60-4" -> ["routes", "60-4"]. */
export function useRoute(): string[] {
  const path = useSyncExternalStore(subscribe, currentPath, () => "/");
  return path
    .split("/")
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment));
}

export function href(...segments: string[]): string {
  return `#/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
}
