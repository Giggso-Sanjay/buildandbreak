# Design — POST /shorten (Odoo #15635)

## Goal
Implement `POST /shorten`: accept a long URL, validate it, and return a
unique 7-character base62 short code — persisting to Postgres and
deduplicating on resubmission of an already-shortened URL. Returns HTTP 200
for both a newly created code and a resubmitted (duplicate) URL (see D-002 —
deviates from TDD.md's original 201-on-create spec).

## Scope
- `app/models/link.py` — `links` table model (code PK, long_url, created_at)
- `app/routes/shorten.py` — POST /shorten handler
- `app/services/code_gen.py` — base62 code generation + collision check
- `migrations/*_create_links_table.*` — new migration for the `links` table
- `tests/test_shorten.py` — core + extended test cases
- `app/db.py` — SQLAlchemy engine/session wiring (see D-001)
- `app/main.py` — FastAPI app entrypoint (see D-001)
- `requirements.txt` — runtime + test dependencies (see D-001)
- `tests/conftest.py` — pytest fixtures (in-memory SQLite test client) (see D-001)

## Acceptance
- POST /shorten with a valid URL returns 200 and a unique 7-char base62 code
- Code is collision-checked against `links.code` before insert
- Resubmitting an already-shortened URL returns the existing code (200), no duplicate row
- Two different POST /shorten calls never return the same code

## Out of scope this session
- GET /{code} redirect (separate task #15636)
- Malformed-URL rejection/422 handling (separate task #15637)
- User accounts, vanity codes, expiration, analytics (out of scope this sprint per PRD)
