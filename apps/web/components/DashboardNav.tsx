"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AccountDrawer } from "./AccountDrawer";
import { LogoMark } from "./editorial/LogoMark";

// Every query mode stays directly in the header, as it always was — the
// clutter complaint turned out to be specifically about the account
// cluster (Connections/theme/name/Sign out) once Connections joined it,
// not about this list. That cluster now lives behind `AccountDrawer`
// instead; this row is untouched.
const LIVE_ITEMS = [
  { label: "Search", href: "/search" },
  { label: "Archaeology", href: "/archaeology" },
  { label: "Who to Ask", href: "/who-to-ask" },
  { label: "Flaky Tests", href: "/flaky-tests" },
  { label: "Notes", href: "/notes" },
  { label: "Weekly Digest", href: "/weekly-digest" },
  { label: "Incidents", href: "/incident-correlation" },
  { label: "Decision Debt", href: "/decision-debt" },
] as const;

export function DashboardNav() {
  const pathname = usePathname();

  return (
    <header className="border-line flex h-16 items-center justify-between border-b px-6 sm:h-18 sm:px-10">
      <div className="flex items-center gap-8">
        <Link href="/" className="flex items-center gap-2">
          <LogoMark className="nav-logo-mark h-7 w-7" />
          <span className="font-serif text-ink text-3xl">Relay</span>
        </Link>
        <nav className="hidden items-center gap-6 sm:flex">
          {LIVE_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                pathname === item.href ? "text-brand" : "text-muted hover:text-ink"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>

      <AccountDrawer />
    </header>
  );
}
