# Session design — Raven E2E sample-app exercise

## Goal

Build a small, standalone, self-contained sample application (a simple
in-memory todo-list manager) across three AI models (Sonnet, Haiku, Opus),
each change genuinely reviewed and signed off, to exercise Raven's
design-gate, signoff-gate, and telemetry pipeline end-to-end. Deliberately
isolated in its own directory — does not touch the real `app/` product code.

## Scope

- `sample_app/*.py`
- `sample_app/tests/*.py`
- `docs/sample_app*.md`

## Acceptance

- Each model contributes one small, real, working Python module or test file
  under the scope above — no placeholder/lorem content.
- Every file is reviewed via `raven-signoff` before its commit (real D4 depth,
  no blind acks).
- All three contributions land as separate commits on
  `feature/raven-e2e-sample-app`, then one PR to `main`.
- Only the two Raven scripts actually needed (`design-helper.py`,
  `signoff-helper.py`) are added under `.claude/scripts/` — not the full
  Raven Enterprise plugin, to avoid shipping proprietary IP to this public
  repo (a real mistake from an earlier round of this exact exercise).
