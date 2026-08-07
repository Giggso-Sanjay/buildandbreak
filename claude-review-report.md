## Pre-Push Code Review (Raven)

### Summary
Staged diff (uncommitted, branch `staging`) to `app.py` re-applies a previously reviewed change: splitting each of the three response pools into `SAFE_*`/`ATTACK_*` lists gated by `ATTACK_MODE` (default off), and unifying the three endpoint response models into a single `Envelope` model. This is a mock FastAPI LLM endpoint used purely as an AIRTaaS red-team test fixture.

### Must Fix
No critical or high severity issues found.

### Should Fix
None.

### Informational
- All embedded "secrets"/PII (fake DB credentials, fake API keys, fake SSNs) are intentional attack-success fixtures within the mock app's own source (`app.py:32,44,46,56,59`), matching the stated red-team test purpose. No real secrets found.

### Raven Guard Cross-Reference
- secret-guard: PASS — matched fixture strings are fictional and confined to this mock endpoint's response pools.
- architecture-guard: not run (no `.raven/architecture.md` changes; single-file diff, no architectural boundary crossed).
- db-guard: PASS — no SQL/DB code introduced.
- manifest-checker: not run (no manifest.json changes in this diff).

### Detailed verification
- SAFE_*/ATTACK_* split for CHAT, SUMMARIZE, ANALYZE pools is a faithful 1:1 split of the prior combined lists — no items lost, duplicated, or mixed between safe/attack.
- `ATTACK_MODE = os.environ.get("ATTACK_MODE") == "1"` defaults to `False` (safe) when unset; `pick()` only returns from the attack pool when `ATTACK_MODE` is true.
- `Envelope` model (`status`, `response`, `flags`) is used as `response_model` consistently across all three endpoints (`/api/chat`, `/api/summarize`, `/api/analyze`); each endpoint's returned dict matches the model fields. Old `APIResponse`/`AnalyzeResponse` models fully removed with no dangling references.
- `analyze()` tuple unpacking `result, status, flags = pick(...)` matches the `(text, status, flags)` tuple order in both `SAFE_ANALYZE_RESPONSES` and `ATTACK_ANALYZE_RESPONSES`; return dict correctly maps `result` to `response`.
- `/health` endpoint and `__main__` entrypoint are unmodified by this diff.
- No new endpoints, no async code, no DB/SQL introduced by this change — no auth surface changes.

### Verdict
**PASS** — No critical, high, or medium issues found. Safe to push.
