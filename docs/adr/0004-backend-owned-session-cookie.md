# ADR 0004: FastAPI owns the login session, not NextAuth.js

**Status:** Accepted — Phase 0

## What

The login OAuth flow (redirect → provider consent → callback → session) is
implemented entirely in the FastAPI backend (`auth/router.py`,
`auth/service.py`). The session is a JWT in an httpOnly cookie, minted by
the backend on successful callback. The Next.js frontend never handles
OAuth client secrets or issues sessions itself — it only redirects the
browser to backend login URLs and reads session state via `GET /v1/auth/me`.

## Why

NextAuth.js is the default choice for OAuth in a Next.js app, and it was
worth seriously considering. It loses here for one structural reason: ADR
0003 requires `auth_identities` to live in Relay's own Postgres database,
addressable by the same `User` model everything else in the backend joins
against. NextAuth's session/account model is designed to own that table
itself (via its own Prisma/database adapter) — bolting it onto a FastAPI-
owned schema means fighting the library's assumptions instead of using them,
for a project where the backend already needs full control of the user
model anyway.

Owning the flow in FastAPI also means there's exactly one place OAuth
client secrets exist, and it's the same service that already needs to store
credentials for the (much higher-stakes) connector flow — one mental model
for "how does Relay talk to an OAuth provider," not two.

**The real cost, discovered while building this, not anticipated up front:**
the session cookie is set during the OAuth *callback*, which is a backend
route (`/v1/auth/{provider}/callback`) — so the cookie is scoped to the
backend's own domain, not the frontend's. In production those are different
domains (e.g. `relay-api.onrender.com` vs. `relay.vercel.app`). That means:

- Client-side `fetch()` calls from the browser straight to the backend
  (with `credentials: "include"`) work fine — the cookie is being sent to
  the domain that set it.
- Next.js **server components cannot read the session** via
  `next/headers` `cookies()` — that API only sees cookies sent to the
  *frontend's* domain on the current request, and this cookie was never set
  there.

That's why the Phase 0 dashboard guard (`components/AuthGuard.tsx`) checks
auth client-side rather than in a server component: it's not a stylistic
choice, it's a consequence of this ADR. If SSR'd authenticated pages are
ever needed, the fix is a BFF proxy under `apps/web/app/api/` (already
anticipated as an empty slot in the repo structure, plan.md §2) that
forwards the session cookie server-to-server — not a same-site cookie hack.

## How

- `core/security.py` — HS256 JWT creation/verification (`create_session_token`,
  `verify_session_token`), signed with `SECRET_KEY`.
- `auth/router.py` — `/login` sets a short-lived `state` cookie (CSRF
  protection) and redirects to the provider; `/callback` verifies `state`,
  exchanges the code, finds-or-creates the user (ADR 0003), and sets the
  `relay_session` cookie (httpOnly, `samesite=lax`, `secure` in production)
  before redirecting to the frontend.
- `core/deps.py` — `get_current_user` / `CurrentUser` dependency, reads the
  cookie and resolves it to a `User` row for any protected route.
- `apps/web/lib/api.ts` — client-side fetch wrapper with
  `credentials: "include"`; `apps/web/components/AuthGuard.tsx` — client
  component that calls `/v1/auth/me` on mount and redirects to `/login` on
  401.
