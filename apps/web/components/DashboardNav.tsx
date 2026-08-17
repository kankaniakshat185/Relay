"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useCurrentUser } from "./AuthGuard";
import { logout } from "@/lib/auth";

const LIVE_ITEMS = [
  { label: "Search", href: "/search" },
  { label: "Connections", href: "/connections" },
] as const;

const UPCOMING_ITEMS = [
  { label: "Archaeology", phase: 2 },
  { label: "Who to Ask", phase: 2 },
  { label: "Flaky Tests", phase: 3 },
  { label: "Dependency Alerts", phase: 4 },
] as const;

export function DashboardNav() {
  const user = useCurrentUser();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <header className="flex items-center justify-between border-b border-neutral-200 px-6 py-4">
      <div className="flex items-center gap-8">
        <Link href="/" className="font-serif text-brand text-xl tracking-tight">
          Relay
        </Link>
        <nav className="flex items-center gap-5">
          {LIVE_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-sm font-medium transition-colors ${
                pathname === item.href
                  ? "text-neutral-900"
                  : "text-neutral-500 hover:text-neutral-900"
              }`}
            >
              {item.label}
            </Link>
          ))}
          {UPCOMING_ITEMS.map((item) => (
            <span
              key={item.label}
              title={`Ships in Phase ${item.phase}`}
              className="cursor-not-allowed text-sm text-neutral-300"
            >
              {item.label}
            </span>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-neutral-600">{user.display_name}</span>
        <button
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
          className="text-sm text-neutral-500 hover:text-neutral-900"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
