"use client";

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "relay-theme";
const THEME_CHANGE_EVENT = "relay-theme-change";

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme: "light" | "dark") {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  // `storage` only fires in *other* tabs, never the one that made the
  // change — this custom event is what lets `useSyncExternalStore` below
  // notice the click in this same tab and re-render.
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
}

function subscribe(callback: () => void) {
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  mql.addEventListener("change", callback);
  window.addEventListener(THEME_CHANGE_EVENT, callback);
  return () => {
    mql.removeEventListener("change", callback);
    window.removeEventListener(THEME_CHANGE_EVENT, callback);
  };
}

function getSnapshot(): "light" | "dark" {
  const stored = localStorage.getItem(STORAGE_KEY);
  // An explicit stored choice always wins; otherwise follow the system —
  // re-derived on every subscribed change, which is what makes an
  // in-progress system-preference change live-update until the user
  // makes their own explicit choice.
  if (stored === "light" || stored === "dark") return stored;
  return systemPrefersDark() ? "dark" : "light";
}

function getServerSnapshot(): "light" | "dark" {
  // The server has no way to know the client's stored preference or
  // system setting — `useSyncExternalStore` reconciles this against the
  // real client snapshot right after hydration, without a mismatch
  // warning; that reconciliation is the point of using this hook here.
  return "light";
}

function SunIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 2v2.5M12 19.5V22M4.22 4.22l1.77 1.77M18.01 18.01l1.77 1.77M2 12h2.5M19.5 12H22M4.22 19.78l1.77-1.77M18.01 5.99l1.77-1.77" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5z" />
    </svg>
  );
}

/** Small icon toggle — follows `prefers-color-scheme` until the user
 * makes an explicit choice, then that choice is persisted (localStorage)
 * and pins `data-theme` on `<html>`. See `globals.css` for the token
 * redefinitions this drives, and `app/layout.tsx`'s `beforeInteractive`
 * script for the other half: setting `data-theme` before hydration so a
 * stored choice doesn't flash the system theme first on load.
 *
 * State comes entirely from `useSyncExternalStore` over
 * localStorage/matchMedia, not `useState` + an effect — this is the
 * correct hook for "external, possibly server/client-divergent source of
 * truth," and avoids the cascading-render footgun of calling `setState`
 * directly inside an effect body just to sync from one. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  return (
    <button
      type="button"
      onClick={() => applyTheme(theme === "dark" ? "light" : "dark")}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className={`text-muted hover:text-ink transition-colors ${className}`}
    >
      {theme === "dark" ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
    </button>
  );
}
