"""Data-access OAuth + provider API clients (GitHub, Slack, Jira).

Distinct from `auth/`: these hold *connector_credentials* (broad, per-provider
data scopes granted post-login), never the login session. Built out starting
Phase 1 — see plan.md §5.
"""
