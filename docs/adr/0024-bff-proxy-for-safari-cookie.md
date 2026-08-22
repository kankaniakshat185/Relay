# ADR 0024: BFF proxy so the session cookie is first-party, not cross-site

**Status:** Accepted

## What

The frontend no longer calls the backend's own domain directly. Every
`apiFetch` call goes to this app's own origin under `/api/v1/*`, which
`next.config.ts`'s `rewrites()` proxies server-side to the real Render
backend. OAuth redirect URIs (login and connector) were moved to match:
`auth/router.py` and `connectors/router.py`'s `_redirect_uri` now build a
URL under `frontend_url + "/api"`, not the backend's own `api_base_url`
(removed from `core/config.py` — nothing reads it anymore). Every
`set_cookie` call's `SameSite` went back to an unconditional `"lax"`
(previously `"none"` in production).

## Why

Documented as a known limitation since the first production deploy (see
the retired paragraph in README's Deployment section): the session cookie
was set on the backend's `onrender.com` domain and sent cross-site by the
frontend's `fetch(..., {credentials: "include"})` calls. That worked in
Chrome but not Safari — Safari's Intelligent Tracking Prevention blocks
third-party cookies on `fetch`/XHR to a different registrable domain
regardless of `SameSite=None; Secure`, which is the only cookie attribute
combination that even permits cross-site delivery in the first place.
There is no cookie flag that fixes this; the browser's own diagnostics at
the time (confirmed live: cookie present in Safari's storage, just never
attached to the request) showed the cookie *itself* wasn't the problem,
the cross-site request shape was.

The fix has to remove the cross-site request, not tune around it. A BFF
(backend-for-frontend) proxy under the frontend's own domain does that:
if the browser only ever addresses `relay.vercel.app`, both the cookie
`Set-Cookie` (minted during the OAuth callback) and every later request
that needs to send it back are same-site by construction, in every
browser, not just the ones with a permissive third-party-cookie policy.

## How

- **`apps/web/next.config.ts`**: added `rewrites()` mapping
  `/api/v1/:path*` → `${BACKEND_API_URL}/v1/:path*`. Next's rewrites are a
  transparent proxy (unlike `redirects()`), so the backend's `Set-Cookie`
  response header passes through attributed to the frontend's own origin
  — this is the one property the whole fix depends on.
- **`apps/web/lib/api.ts`**: `API_URL` changed from
  `NEXT_PUBLIC_API_URL` (the backend's real, browser-visible URL) to the
  constant `"/api"`. Every caller (`notes.ts`, `connectors.ts`,
  `loginUrl`) picks this up automatically — none of them needed their own
  change.
- **`BACKEND_API_URL`** (new, server-only, no `NEXT_PUBLIC_` prefix): the
  real Render URL, read only inside `next.config.ts` at request time on
  Vercel's server, never shipped to the browser. Replaces
  `NEXT_PUBLIC_API_URL` in `.env.example`.
- **`auth/router.py` / `connectors/router.py`**: `_redirect_uri` now
  points at `frontend_url + "/api" + api_v1_prefix + ...` instead of
  `api_base_url + api_v1_prefix + ...`. This is what every OAuth
  provider's registered callback URL had to change to match — the
  backend's own domain is no longer a valid redirect target for any of
  the six apps (GitHub login, GitHub connector, Slack login, Slack
  connector, Google login, Jira connector).
- **`core/config.py`**: `api_base_url` removed — nothing reads it once
  both `_redirect_uri` functions no longer do.
- **Cookies**: `SameSite` simplified to `"lax"` unconditionally. `"none"`
  was only ever a workaround for the cross-site case this ADR removes;
  keeping it would just be an unnecessarily loose policy now that the
  request is genuinely same-site in every environment, not a correctness
  requirement either way.

## Consequences

- Fixes Safari (and any other browser enforcing similar cross-site
  cookie policy) without a client-side workaround — the request shape
  itself is now first-party, so there's nothing browser-specific left to
  break.
- The backend is no longer directly reachable from the browser for any
  authenticated route — only through the frontend's proxy (or directly,
  unauthenticated, for `/healthz`). CORS middleware in `main.py` is now
  effectively dead code for browser traffic (nothing cross-origin reaches
  it anymore); left in place rather than removed, since it's harmless and
  still relevant for direct backend testing (Swagger UI, `curl`).
- One more moving part in local dev: `apps/web/.env.local` needs
  `BACKEND_API_URL` (defaults to `http://localhost:8000`, matching the
  existing local FastAPI dev server, so this is a no-op for anyone
  following the README's existing setup steps as written).
- Not yet live-verified in Safari post-fix — this ADR records the design
  and the code change; the actual redeploy + Safari retest is a manual
  follow-up once the new OAuth redirect URIs are registered on all six
  provider dashboards.
