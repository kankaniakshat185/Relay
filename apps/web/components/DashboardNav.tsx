"use client";

import Link from "next/link";

import { LogoMark } from "./editorial/LogoMark";
import { NavMenu } from "./NavMenu";

// Every actual nav item (query modes, Connections, theme, Sign out) now
// lives inside `NavMenu`'s expanding panel — this header is just
// branding plus the one trigger that opens it. The old approach (a
// growing row of links, then a growing right-side cluster once
// Connections/theme/name/Sign out got added there too) ran out of room
// the moment a second new feature showed up; a single entry point with
// unlimited room behind it doesn't.
export function DashboardNav() {
  return (
    <header className="border-line relative z-50 flex h-16 items-center justify-between border-b px-6 sm:h-18 sm:px-10">
      <Link href="/" className="flex items-center gap-2">
        <LogoMark className="nav-logo-mark h-7 w-7" />
        <span className="font-serif text-ink text-3xl">Relay</span>
      </Link>
      <NavMenu />
    </header>
  );
}
