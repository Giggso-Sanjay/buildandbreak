# Decisions — recorded deviations from the frozen design

Append-only. Entries are written at the moment of deviation (agent-recorded or via /raven-decide). scope=global means a departure from .raven/design/global.md.

## D-1 · 2026-08-04T08:56:40.704907+00:00 · scope=local · session=unknown

**Before:** Frozen scope listed 5 files: app/models/link.py, app/routes/shorten.py, app/services/code_gen.py, migrations/*_create_links_table.sql, tests/test_shorten.py

**After:** Added app/db.py, app/main.py, requirements.txt, tests/conftest.py

**Why:** A runnable FastAPI app and pytest harness cannot exist without an entrypoint, DB engine/session wiring, declared dependencies, and a test client fixture -- these are load-bearing infra for the 5 scoped files, not new features or scope creep

**Alternatives considered:** None considered as viable -- these files are mechanically required for the scoped code to run or be tested at all; there was no alternative that avoided creating them

**Design:** 22698d5e4812 → 235d8eaf7af9

## D-2 · 2026-08-04T08:56:56.505231+00:00 · scope=local · session=unknown

**Before:** TDD.md core test + frozen design.md: POST /shorten on a newly created URL returns 201; resubmitting an already-shortened URL returns 200 with the existing code

**After:** POST /shorten returns 200 for both a newly created code and a resubmitted (duplicate) URL -- 201 is no longer used

**Why:** Explicit developer instruction ('instead of 201 return status code as 200'). Assistant flagged before making the change that this breaks TDD.md's non-negotiable core test (201-on-create); developer confirmed to proceed anyway and apply it to both paths

**Alternatives considered:** Keeping 201-on-create / 200-on-duplicate per the original TDD spec -- rejected in favor of 200 for both, per explicit developer instruction. TDD.md itself has NOT yet been updated to reflect this change -- it currently still documents 201 as the core test, so it now disagrees with the implemented/frozen behavior until updated

**Design:** 235d8eaf7af9 → 235d8eaf7af9
