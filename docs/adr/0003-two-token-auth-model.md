# ADR 0003: Two separate token models for login vs. data-access

**Status:** Accepted — Phase 0

## What

Login identity and connector data-access are two structurally separate
concerns, backed by two separate tables: `auth_identities` (Phase 0, built
now) and `connector_credentials` (Phase 1, not built yet — lives under
`connectors/`). A user having a login identity for a provider (e.g. signed
in with GitHub) never implies Relay can read that provider's data.

## Why

The obvious shortcut is "the user OAuth'd with GitHub to sign in, so we
already have a GitHub token — just use it to read their repos too." That
shortcut breaks in a specific, predictable way: **login only needs identity
scopes** (`read:user`, email), while the context-search/archaeology/who-to-
ask features need much broader scopes (repo read, possibly org access,
channel history, Jira project access). If login and connector access share
one token, either:

- Login requests broad scopes it doesn't need, which is a worse consent
  screen and a bigger blast radius if that token ever leaks, or
- Someone assumes "logged in with GitHub" means "GitHub data is readable"
  and ships a feature that silently 401s the first time a user who signed
  in but never visited the Connections page tries to use it.

Keeping them structurally separate — different tables, different scopes,
independently revocable — makes the second failure mode impossible to reach
by accident. It also means a user can disconnect Jira without logging out,
and log out without losing a connected GitHub integration.

## How

- `auth/models.py`: `User` + `AuthIdentity` (provider, provider_user_id,
  provider_email — identity only, no access token stored beyond what's
  needed to complete the OAuth handshake).
- `connectors/*` (Phase 1): `connector_credentials` table, keyed by
  (user_id, provider), storing the actual access/refresh tokens used to
  call GitHub/Slack/Jira APIs on the user's behalf.
- The frontend must not assume login implies a connector is present — the
  Connections page (Phase 1) is where that state is surfaced and where the
  user explicitly grants each provider's broader scopes.
- Same provider, two rows: a user who signs in with GitHub *and* connects
  GitHub for data access has one `auth_identities` row and one
  `connector_credentials` row, unrelated to each other beyond sharing a
  `user_id`.
