# TDD — URL Shortener Service (Sprint 1)

## Storage
Postgres, one table: `links(code PK, long_url, created_at)`.

## Code generation
7-character base62 string, collision-checked against `links.code` before insert.

## Core test cases (non-negotiable)
- `POST /shorten` with a valid URL returns `201` + a unique code.
- `GET /{code}` for an existing code returns `302` to the stored `long_url`.
- `GET /{code}` for an unknown code returns `404`.
- `POST /shorten` with a malformed URL (no scheme, empty string) returns `422`.
- Two different `POST /shorten` calls never return the same code.

## Extended test cases
- `POST /shorten` with a URL that's already been shortened returns the
  existing code instead of creating a duplicate row.
- Short codes are case-sensitive.
