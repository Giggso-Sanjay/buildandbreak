# Session Design — enrich /health endpoint

## Scope
- app/main.py

## Acceptance
- `GET /health` returns `{"status": "ok", "version": <app version>, "uptime_s": <float>, "timestamp": <ISO8601 UTC>}` instead of just `{"status": "ok"}`.
- No other route, model, or behavior in app/main.py changes.
- App start time is recorded at startup (existing `on_startup` handler) to compute uptime.
