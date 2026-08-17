# Decision 0003: Editorial visual system, not a generic SaaS dashboard

**Status:** Decided — post-Phase 1

## What

The frontend was rebuilt around a deliberate editorial design system —
large serif display type (Bodoni Moda), a red/off-white/near-black palette,
sharp (non-rounded) geometry, thin 1px rules defining a 12-column grid, and
oversized typography used as a graphic element — replacing the generic
rounded-card Tailwind-SaaS look Phase 0/1 shipped with. Scope: the login
page, dashboard nav, dashboard home, Connections, and Search — every page
that existed at the time, not just the landing page.

## Why

The functional Phase 1 UI worked, but it read as an interchangeable
SaaS-template dashboard: centered cards, pill buttons, generic spacing —
nothing about the visual language communicated what Relay actually is
(a precise, technical correlation engine) versus what a thousand other
CRUD dashboards look like. This was a direct, detailed art-direction
request, not something inferred — the brief specified the reference
aesthetic (editorial/Swiss-grid, oversized type, asymmetric composition,
red as composition rather than decoration), explicit design tokens, and a
page-by-page treatment.

The decision worth recording isn't "use red" (that's a token value, not an
architecture call) — it's the shift from **styling pages individually** to
**building a small set of shared editorial primitives** that every page
composes from. That's what keeps five pages feeling like one product
instead of five separately-designed ones, and it's the thing a future
contributor needs to know to extend Phase 2+ pages consistently.

## How

- `app/globals.css` — the only place raw color/token values live
  (`--relay-red`, `--relay-black`, `--relay-off-white`, etc.), mapped into
  Tailwind v4's `@theme inline` as `brand`, `ink`, `paper`, `muted`, `line`.
  Sharp corners are the default (`border-radius: 0` on inputs/buttons/links)
  — a component opts into rounding, not the other way around.
- `app/layout.tsx` — Bodoni Moda (variable weight, for real bold weight at
  200px+ headline sizes) as the one display serif; Geist Sans stays for
  body/UI text.
- `components/editorial/` — the shared primitives every page draws from:
  `DisplayHeading` (centralized type scale, `hero`/`xl`/`lg`/`md`),
  `SectionLabel` (tracked uppercase metadata), `Rule`/`VerticalRule` (the
  1px lines that define the grid), `EditorialButton`/`EditorialLinkButton`
  (rectangular, arrow-on-hover, no pill), `RedPanel` (full red block as
  composition), `Metadata` (dot-separated tracked metadata rows), `Footer`.
  Pages compose these rather than hand-rolling card/button markup per page.
- Each page uses a 12-column grid (`grid-cols-12` + `col-span-*`) with
  intentionally asymmetric spans — not every section is 50/50.
- No new dependencies for animation — hover/transition effects are plain
  CSS transitions (underline/color/translate), matching the brief's
  "subtle, editorial, not Framer Motion" direction.
- Functionality untouched: same routes, same API calls (`lib/api.ts`,
  `lib/connectors.ts`, `lib/contextSearch.ts`), same auth flow
  (`AuthGuard`), same state management. This was a presentation-layer
  rebuild, verified by keeping `next build`/`eslint` green throughout and
  confirming every route still statically prerenders without error.
