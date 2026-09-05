"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useCurrentUser } from "./AuthGuard";
import { ThemeToggle } from "./ThemeToggle";
import { Rule } from "./editorial/Rule";
import { SectionLabel } from "./editorial/SectionLabel";
import { logout } from "@/lib/auth";
import {
  type ConnectorProvider,
  type ConnectorStatus,
  fetchConnectors,
} from "@/lib/connectors";

// The same seven query modes `DashboardNav` shows directly — repeated
// here, not moved here. Vox's own drawer duplicates its top-bar category
// links rather than being the only place to find them (see the
// reference image), and that's the right call for us too: the nav stays
// the fast path, this is the "everything, generously laid out" path.
const NAV_ITEMS = [
  { label: "Search", href: "/search" },
  { label: "Archaeology", href: "/archaeology" },
  { label: "Who to Ask", href: "/who-to-ask" },
  { label: "Flaky Tests", href: "/flaky-tests" },
  { label: "Notes", href: "/notes" },
  { label: "Weekly Digest", href: "/weekly-digest" },
  { label: "Incidents", href: "/incident-correlation" },
] as const;

const PROVIDER_LABELS: Record<ConnectorProvider, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
};

function connectorSummary(status: ConnectorStatus): string {
  return `${PROVIDER_LABELS[status.provider]} · ${status.connected ? "Connected" : "Not connected"}`;
}

function MenuIcon({ className }: { className?: string }) {
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
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
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
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

/** Slides in from the right over a dimmed backdrop: account info up top,
 * then one Vox-style divided list — every query mode, Connections, and
 * Sign out as large serif rows, each closed off by its own hairline
 * rule — instead of `DashboardNav`'s compact row. That nav stays exactly
 * as it was; this is a second, roomier way to get anywhere, not a
 * replacement for it. */
export function AccountDrawer() {
  const user = useCurrentUser();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [connectors, setConnectors] = useState<ConnectorStatus[] | null>(null);

  useEffect(() => {
    if (open && connectors === null) {
      fetchConnectors()
        .then(setConnectors)
        .catch(() => setConnectors([]));
    }
  }, [open, connectors]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open]);

  function rowClass(active: boolean) {
    return `font-serif block py-4 text-2xl transition-colors sm:text-3xl ${
      active ? "text-brand" : "text-ink hover:text-brand"
    }`;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-label="Open menu"
        className="border-line text-ink hover:border-ink flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-colors"
      >
        <MenuIcon className="h-4 w-4" />
      </button>

      {/* Backdrop — click to close, dims the rest of the page rather than
          the drawer sharing space with it. */}
      <div
        onClick={() => setOpen(false)}
        aria-hidden="true"
        className={`fixed inset-0 z-40 bg-black/40 transition-opacity duration-300 ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      <div
        className={`bg-paper border-line fixed inset-y-0 right-0 z-50 w-[360px] border-l shadow-lg transition-transform duration-300 ease-out sm:w-[420px] ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col overflow-y-auto px-8 py-8 sm:px-10 sm:py-10">
          <div className="flex items-center justify-between">
            <SectionLabel tone="brand">Menu</SectionLabel>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close menu"
              className="text-ink hover:text-brand transition-colors"
            >
              <CloseIcon className="h-5 w-5" />
            </button>
          </div>
          <p className="text-muted mt-4 text-sm">Signed in as {user.display_name}</p>

          {/* Utility row — theme is a control, not a destination, so it
              gets Vox's WATCH/LISTEN/PLAY treatment (a single row above
              the divided list) instead of a list item of its own. */}
          <div className="mt-8 flex items-center justify-between">
            <SectionLabel>Theme</SectionLabel>
            <ThemeToggle />
          </div>

          <Rule className="mt-8" />

          <nav className="flex flex-col">
            {NAV_ITEMS.map((item) => (
              <div key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className={rowClass(pathname === item.href)}
                >
                  {item.label}
                </Link>
                <Rule />
              </div>
            ))}

            <div>
              <Link
                href="/connections"
                onClick={() => setOpen(false)}
                className={rowClass(pathname === "/connections")}
              >
                Connections
              </Link>
              <div className="mb-4 flex flex-col gap-1">
                {(connectors ?? []).map((status) => (
                  <p key={status.provider} className="text-muted text-sm">
                    {connectorSummary(status)}
                  </p>
                ))}
                {connectors === null && (
                  <p className="text-muted text-sm">Checking connections…</p>
                )}
              </div>
              <Rule />
            </div>

            <button
              type="button"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
              className={`${rowClass(false)} text-left`}
            >
              Sign out
            </button>
          </nav>
        </div>
      </div>
    </>
  );
}
