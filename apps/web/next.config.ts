import type { NextConfig } from "next";

// Server-only — the real Render backend URL, never sent to the browser.
// Defaults to the local FastAPI dev server so this works out of the box
// with the README's local-dev setup too, not just in production.
const BACKEND_API_URL = process.env.BACKEND_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  /**
   * BFF proxy (ADR 0024): every `/api/v1/*` request the browser makes is
   * rewritten server-side to the real backend, so from the browser's
   * perspective it only ever talks to this app's own origin. That's what
   * makes the session cookie genuinely first-party — Safari's ITP blocks
   * cross-site cookies on `fetch`/XHR regardless of `SameSite=None`, and
   * there's no cookie attribute that works around that; the fix is
   * removing the cross-site request entirely, not tuning the cookie.
   *
   * `rewrites()` proxies transparently (unlike `redirects()`): the
   * `Set-Cookie` response header from the backend passes straight
   * through, attributed to this origin, not the backend's. That covers
   * both the OAuth callback (which mints the cookie) and every later
   * `apiFetch` call (which needs to send it back) — see `lib/api.ts`.
   */
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_API_URL}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
