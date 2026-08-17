"use client";

import Link from "next/link";

import { useCurrentUser } from "@/components/AuthGuard";

const ROADMAP = [
  { phase: 1, label: "Connections + Context Searcher", status: "live" },
  { phase: 2, label: "Codebase Archaeology + Who Should I Ask", status: "upcoming" },
  { phase: 3, label: "Flaky Test Investigator", status: "upcoming" },
  { phase: 4, label: "Dependency Alert Bot", status: "upcoming" },
] as const;

export default function DashboardHome() {
  const user = useCurrentUser();

  return (
    <div className="max-w-3xl">
      <p className="text-xs tracking-[0.2em] text-neutral-400 uppercase">Signed in</p>
      <h1 className="font-serif mt-2 text-4xl text-neutral-900">{user.display_name}</h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-600">
        Connecting GitHub, Slack, and Jira for data access is a separate step from signing in —
        head to Connections to get started.
      </p>

      <Link
        href="/connections"
        className="bg-brand text-brand-foreground mt-6 inline-flex h-11 items-center rounded-md px-5 text-sm font-medium"
      >
        Connect your accounts
      </Link>

      <div className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-neutral-200 bg-neutral-200 sm:grid-cols-4">
        {ROADMAP.map((item) => (
          <div key={item.phase} className="bg-white p-4">
            <p className="font-serif text-brand text-2xl">{item.phase}</p>
            <p className="mt-1 text-xs leading-snug text-neutral-600">{item.label}</p>
            <p
              className={`mt-2 text-[11px] font-medium tracking-wide uppercase ${
                item.status === "live" ? "text-brand" : "text-neutral-300"
              }`}
            >
              {item.status}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
