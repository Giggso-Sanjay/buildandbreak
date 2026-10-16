# Decisions — recorded deviations from the frozen design

Append-only. Entries are written at the moment of deviation (agent-recorded or via /raven-decide). scope=global means a departure from .raven/design/global.md.

## D-1 · 2026-07-17T13:59:23.842831+00:00 · scope=local · session=unknown

**Before:** Scope limited to sample_app/*.py, sample_app/tests/*.py, docs/sample_app*.md

**After:** Also write .raven/state/active-card.json recording the real card 15069 as the active card, via card_link.py's own set_active_card() function

**Why:** Root-caused why /intel/odoo-close-candidates on the Hub shows empty even though PR 8 is now genuinely merged and card 15069 is still open: card_id was never stamped into pr_timings because the branch-to-card resolution (card_link.py resolve_card_id) never had anything to resolve from - no commit trailer, no active-card state file, and the branch name has no numeric card id in it. The real linkage for card 15069 was done earlier via direct SQL on a different table (contribute_attributions), never through this branch-mapping path

**Alternatives considered:** Hand-edit the JSON file directly instead of going through set_active_card() - rejected, since that function is the established, tested entry point raven-fetch itself uses, and using it keeps the write consistent with real usage rather than a one-off shortcut

**Design:** 267e5f130717 → 267e5f130717

## D-2 · 2026-07-18T21:59:17.488657+00:00 · scope=local · session=unknown

**Before:** TodoList has no priority concept; list() only supports include_done filter

**After:** Task gains priority:int=0; add() validates it; list() gains sort_by_priority to order by (-priority, id)

**Why:** Round 2 of Raven E2E exercise needs a genuine non-trivial change within the frozen sample_app scope to give signoff/pre-pr real surface area, rather than a no-op diff

**Alternatives considered:** (none recorded)

**Design:** 267e5f130717 → 267e5f130717

**Global section:** Scope
