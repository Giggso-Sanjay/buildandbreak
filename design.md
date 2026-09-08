# Session design — /sum endpoint

## Goal

Add a small, stateless utility endpoint to the FastAPI app that accepts two
numeric values and returns their sum.

## Scope

- `app/main.py`
- `app/tests/test_main.py`

## Acceptance

- `POST /sum` accepts `{"a": <number>, "b": <number>}` and returns
  `{"result": <number>}` with the correct sum (ints and floats).
- Non-numeric input returns FastAPI's standard 422 validation error.
- No auth required (public endpoint, same class as `/health`).
- New tests in `app/tests/test_main.py` cover: integer sum, float sum,
  negative numbers, and invalid (non-numeric) input.

## Approval

Approved by developer (one-word ack: "approved").
