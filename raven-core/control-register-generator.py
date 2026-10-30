#!/usr/bin/env python3
"""
Raven — Control Register Generator v1.0 (task T26)

Converts raven-decision-map's placement-plan JSON (ast_decision_scanner.py's output —
the same shape guardrail-injector.py and post-scan-comments.py already consume) into
Section G's Control Register: an audit-queryable, machine-readable record of controls
that actually exist, each with a control label, an owner, and an evidence pointer.

Scope, stated honestly (first pass, per the CSV's own note — "not yet synced to a live
audit system"): this register only covers *logging* controls the scanner can directly
verify are in place — placement-plan entries where `existing_log_status == "sufficient"`.
Guardrail (tool_call) controls from T19/T32 are a different kind of evidence (a decorator
was injected and actually runs at call time) that this scanner's placement plan alone
cannot confirm — confirming *that* needs correlating T19's injector output or T32's
runtime `tool_call.denied`/`*_screen.evaluated` events against a specific commit, which
is genuinely separate integration work, not something to fake here by guessing. A future
task, not an assumption baked into this one.

Output: one row per covered entry —

    {
      "control": "<decision class> logging: <recommended_event_name>",
      "owner": "<from T11's resolve_owner, or \"\" if unresolved>",
      "evidence_pointer": "<file>:<line>",
      "decision_classes": [...],
      "mandatory_status": "...",
      "risk_category": [...]
    }

Emitted as YAML by default (Section G: "YAML/JSON") using a minimal, stdlib-only,
JSON-literal-scalar emitter — this repo's agent scripts are stdlib-only (no PyYAML
dependency), and YAML's flow style is a strict superset of JSON syntax, so every scalar/
sequence below is simultaneously valid JSON and valid YAML; nothing here needs a real
YAML parser/emitter library to produce well-formed output.

Usage:
    cat placement-plan.json | python3 control-register-generator.py
    cat placement-plan.json | python3 control-register-generator.py --format json
    cat placement-plan.json | python3 control-register-generator.py --out .raven/control-register.yaml

Exit codes: 0 = ran (regardless of row count) | 2 = usage/parse error (fail-open,
matching this repo's other placement-plan consumers, e.g. guardrail-injector.py)
"""

import argparse
import json
import sys


def build_rows(entries: list) -> list:
    """One row per placement-plan entry whose logging control is verified
    already in place. Order preserved from input (the scanner's own scan
    order), not re-sorted — a register is a record, not a ranked report."""
    rows = []
    for entry in entries:
        if entry.get("existing_log_status") != "sufficient":
            continue
        classes = entry.get("decision_classes", []) or []
        label = f"{classes[0]} logging: {entry.get('recommended_event_name', '')}" if classes \
            else f"logging: {entry.get('recommended_event_name', '')}"
        rows.append({
            "control": label,
            "owner": entry.get("owner", "") or "",
            "evidence_pointer": f"{entry.get('file', '')}:{entry.get('line', '')}",
            "decision_classes": classes,
            "mandatory_status": entry.get("mandatory_status", ""),
            "risk_category": entry.get("risk_category", []) or [],
        })
    return rows


# ── minimal stdlib-only YAML emission (see module docstring) ───────────────

_FIELD_ORDER = ("control", "owner", "evidence_pointer", "decision_classes",
                "mandatory_status", "risk_category")


def to_yaml(rows: list) -> str:
    if not rows:
        return "[]\n"
    lines = []
    for row in rows:
        first = True
        for key in _FIELD_ORDER:
            if key not in row:
                continue
            prefix = "- " if first else "  "
            first = False
            lines.append(f"{prefix}{key}: {json.dumps(row[key])}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Raven Control Register Generator")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml")
    parser.add_argument("--out", default=None, help="Write to this path instead of stdout")
    args = parser.parse_args()

    raw = sys.stdin.read()
    try:
        entries = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError as e:
        print(f"❌ Invalid placement-plan JSON on stdin: {e}", file=sys.stderr)
        sys.exit(2)

    rows = build_rows(entries)
    output = to_yaml(rows) if args.format == "yaml" else json.dumps(rows, indent=2) + "\n"

    if args.out:
        from pathlib import Path
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output, encoding="utf-8")
        print(f"✅ wrote {len(rows)} control-register row(s) to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠️  control-register-generator: unexpected error — {e} (fail-open)", file=sys.stderr)
        sys.exit(2)
