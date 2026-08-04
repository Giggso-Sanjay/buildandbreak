# PRD — URL Shortener Service (Sprint 1)

## Goal
A minimal service that shortens a long URL into a short code and redirects
visitors from the short code back to the original URL.

## Scope — features this sprint
1. `POST /shorten` — accept a long URL, return a short code.
2. `GET /{code}` — redirect to the original URL.
3. Reject invalid/malformed URLs at creation time.

## Out of scope (future sprints)
- User accounts / per-user link ownership
- Custom/vanity short codes
- Click analytics
- Link expiration
