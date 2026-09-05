# ADR 0028: Split navigation — query modes stay in the header, account actions move to a drawer

**Status:** Accepted

## What

The header nav no longer grows without bound as features ship. Every
query mode (all eight, as of Decision Debt) stays directly visible in
`DashboardNav`, exactly as it always was. Everything account-related
(Connections + live per-provider status, who's signed in, Sign out) now
lives in `AccountDrawer` — a panel that slides in from the right over a
dimmed backdrop, triggered by one icon button, duplicating the query-mode
list inside it in a roomier, large-serif-type layout. Theme stays visible
in the header itself, beside the drawer's own trigger — reached for too
often to bury behind a click.

## Why

**The actual clutter complaint was narrower than it first looked.**
Adding a `Connections` link to the header's right side (alongside theme,
name, Sign out) was what triggered "the navbar looks too cluttered, and
it gets worse with every new button" — but the diagnosis mattered: the
query-mode list itself was never the problem, only the account cluster
once a fourth item joined it. The first fix attempt (a single hamburger
menu replacing *everything*, query modes included) over-corrected —
reverted once it was clear the direct nav row was fine and only the
account side needed to change.

**Why a drawer, not a dropdown.** A small dropdown was the initial plan
(and one option formally offered) for the account cluster specifically.
Superseded by a Vox-style slide-in drawer instead, once shown as a
concrete reference: more room for live connection status per provider,
room to duplicate the query-mode list at a size worth reading rather than
cramming it into a dropdown's tight vertical space, and a pattern this
design system had reason to adopt for its own sake (an explicit editorial
"contents page" feel, not just a menu).

**Why duplicate the query-mode list inside the drawer at all**, rather
than making it Connections-only. Modeled directly on Vox's own reference
UI, which duplicates its top-bar category links inside its expanding
panel rather than treating the panel as account-only. The nav stays the
fast path for someone who already knows where they're going; the drawer
is the "everything, laid out generously" path — not a replacement for
the nav, a second way to reach the same destinations.

**Why the drawer opens from the right, not the left.** Tried left first
(matching one interpretation of the Vox reference, which itself opens
from the right) — corrected on direct instruction to dock right instead,
which is also where the trigger button sits, so the drawer now opens
from the same side its own trigger lives on.

**Why the repo picker on Decision Debt's page was rebuilt to match
`RepoFilePicker` instead of using its own design.** A one-off styled
repo list was built for that page's initial version — flagged as
inconsistent with the picker already shared by Archaeology, Who Should I
Ask, and Incident Correlation. Rebuilt to use the exact same markup
(`SectionLabel` + `Rule` header, `border-line border-b` rows, `text-brand`
selected state) rather than extracting a fully shared component, since
Decision Debt only needs repo-level selection, not `RepoFilePicker`'s
file/directory browsing — matching the *design*, not the component
itself, was the actual ask.

## How

- **`DashboardNav.tsx`**: unchanged query-mode row; the account cluster
  (Connections/name/Sign out) removed from here entirely, replaced by
  `<ThemeToggle />` and `<AccountDrawer />` side by side.
- **`AccountDrawer.tsx`**: a client component owning its own open/close
  state, a backdrop (`fixed inset-0`, click-to-close), and the sliding
  panel itself (`fixed inset-y-0 right-0`, `translate-x-full` ↔
  `translate-x-0`). Duplicates the same `NAV_ITEMS` list `DashboardNav`
  renders directly, plus Connections (with `fetchConnectors` called
  lazily on open, not on every page load) and Sign out. Closes on `Esc`,
  on backdrop click, or automatically on route change.
- **Decision Debt's repo picker**: inlined the same list markup
  `RepoFilePicker`'s pre-selection view uses, rather than importing that
  component (which would also pull in file/directory browsing this page
  doesn't need).

## Consequences

- The header's own item count is now stable at "however many query modes
  exist," independent of how the account cluster grows — the actual
  problem this ADR set out to fix.
- Two places now list every query mode (the header and the drawer) —
  matching Vox's own precedent deliberately, not an oversight, but a real
  thing to keep in sync: a ninth query mode needs both `LIVE_ITEMS`
  (`DashboardNav.tsx`) and `NAV_ITEMS` (`AccountDrawer.tsx`) updated, not
  just one.
