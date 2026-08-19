"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useCurrentUser } from "./AuthGuard";
import { LogoMark } from "./editorial/LogoMark";
import { logout } from "@/lib/auth";

const LIVE_ITEMS = [
  { label: "Search", href: "/search" },
  { label: "Archaeology", href: "/archaeology" },
  { label: "Who to Ask", href: "/who-to-ask" },
  { label: "Connections", href: "/connections" },
] as const;

const UPCOMING_ITEMS = [
  { label: "Flaky Tests", phase: 3 },
  { label: "Dependency Alerts", phase: 4 },
] as const;

export function DashboardNav() {
  const user = useCurrentUser();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <header className="border-line flex h-16 items-center justify-between border-b px-6 sm:h-18 sm:px-10">
      <div className="flex items-center gap-8">
        <Link href="/" className="flex items-center gap-2">
          <LogoMark className="h-7 w-7" />
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
          {UPCOMING_ITEMS.map((item) => (
            <span
              key={item.label}
              title={`Ships in Phase ${item.phase}`}
              className="text-line cursor-not-allowed text-xs font-medium tracking-[0.15em] uppercase"
            >
              {item.label}
            </span>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-5">
        <span className="text-muted hidden text-xs tracking-[0.1em] uppercase sm:inline">
          {user.display_name}
        </span>
        <button
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
          className="text-xs font-medium tracking-[0.15em] text-ink uppercase transition-colors hover:text-brand"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
