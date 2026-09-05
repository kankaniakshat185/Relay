"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

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

// Every query-mode page lives here, and only here — this is the one list
// that grows with the product (Incident Correlation just joined,
// Decision Debt is next) without ever widening the persistent header,
// which is the entire reason this panel exists instead of a growing row
// of nav links.
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

function connectorSummary(status: ConnectorStatus): string {
  return `${PROVIDER_LABELS[status.provider]} · ${status.connected ? "Connected" : "Not connected"}`;
}

/** The single entry point to everything that isn't the current page —
 * every query-mode link, Connections (with live status inline), theme,
 * and Sign out. Replaces what used to be a growing row of nav links plus
 * a separate account cluster; see `DashboardNav`'s own comment for why
 * both were collapsed into this one trigger. */
export function NavMenu() {
  const user = useCurrentUser();
  const router = useRouter();
  const pathname = usePathname();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [connectors, setConnectors] = useState<ConnectorStatus[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Connection status is fetched lazily, once per panel session, not on
  // every page load — nobody needs it until they actually open this.
  useEffect(() => {
    if (open && connectors === null) {
      fetchConnectors()
        .then(setConnectors)
        .catch(() => setConnectors([]));
    }
  }, [open, connectors]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // "/" opens (skipped while any text input already has focus, so it
  // doesn't hijack typing elsewhere), "Escape" closes.
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      const typing = (document.activeElement as HTMLElement | null)?.tagName === "INPUT";
      if (e.key === "/" && !open && !typing) {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open]);

  // A route change means a link inside the panel was just followed —
  // close it rather than leaving it open over the new page. Adjusting
  // state directly during render (React's own recipe for "reset state
  // when a prop changes") rather than in an effect, which would set
  // state synchronously on every render and trigger a cascade.
  const [lastPathname, setLastPathname] = useState(pathname);
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setOpen(false);
    setQuery("");
  }

  const filtered = NAV_ITEMS.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        className="border-line text-ink hover:border-ink flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-colors"
      >
        {open ? <CloseIcon className="h-4 w-4" /> : <MenuIcon className="h-4 w-4" />}
      </button>

      <div
        className={`border-line bg-paper fixed inset-x-0 top-16 z-40 overflow-hidden border-b shadow-lg transition-[max-height,opacity] duration-300 ease-out sm:top-18 ${
          open ? "max-h-[85vh] opacity-100" : "max-h-0 opacity-0"
        }`}
      >
        <div className="mx-auto max-w-[1600px] px-6 py-10 sm:px-10">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a page… (press / to open, esc to close)"
            className="text-ink placeholder:text-muted border-line w-full border-b bg-transparent pb-3 font-serif text-xl focus:outline-none sm:text-2xl"
          />

          <div className="mt-10 grid grid-cols-1 gap-x-16 gap-y-10 sm:grid-cols-[2fr_1fr]">
            <div>
              <SectionLabel tone="brand">Query Modes</SectionLabel>
              {filtered.length === 0 ? (
                <p className="text-muted mt-4 text-sm">No page matches &ldquo;{query}&rdquo;.</p>
              ) : (
                <ul className="mt-4 flex flex-col">
                  {filtered.map((item) => (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={`font-serif block py-1.5 text-2xl transition-colors sm:text-3xl ${
                          pathname === item.href ? "text-brand" : "text-ink hover:text-brand"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex flex-col gap-6">
              <div>
                <SectionLabel tone="brand">Account</SectionLabel>
                <p className="text-muted mt-3 text-xs">Signed in as {user.display_name}</p>
                <Link
                  href="/connections"
                  className={`mt-3 block text-sm font-medium transition-colors ${
                    pathname === "/connections" ? "text-brand" : "text-ink hover:text-brand"
                  }`}
                >
                  Connections
                </Link>
                <div className="mt-2 flex flex-col gap-1">
                  {(connectors ?? []).map((status) => (
                    <p key={status.provider} className="text-muted text-xs">
                      {connectorSummary(status)}
                    </p>
                  ))}
                  {connectors === null && (
                    <p className="text-muted text-xs">Checking connections…</p>
                  )}
                </div>
              </div>

              <Rule />

              <div className="flex items-center justify-between">
                <SectionLabel>Theme</SectionLabel>
                <ThemeToggle />
              </div>

              <button
                type="button"
                onClick={async () => {
                  await logout();
                  router.replace("/login");
                }}
                className="text-ink hover:text-brand w-fit text-xs font-medium tracking-[0.15em] uppercase transition-colors"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
