#!/usr/bin/env python3
"""
Raven — Decision-Map Gate v1.0

Hard-blocking pre-commit gate: fails the commit if ANY mandatory decision
point anywhere in the whole project — not just this commit's diff, per the
project's explicit choice to scope this gate to the full repo rather than
raven-refresh's usual diff-only posture — is missing sufficient raven_log()
evidence, per raven-decision-map's own classification.

Blocks on ANY real decision-point finding — both "mandatory" (high-confidence,
>=0.85: retry/circuit-breaker decorators, try/except recovery, state-attribute
assignment, auth-guard calls, non-stdlib dependency calls) and "recommended"
(lower-confidence pattern matches: Routing/Eligibility/Outcome) — as long as
existing_log_status != "sufficient". Two categories are deliberately excluded,
not as a loophole but because including them would be blocking on the wrong
thing entirely:
  - "no-log" entries — the scanner's own explicit exemption (pure
    calculations, getters, small helpers) — blocking on these would mean
    blocking BECAUSE a function correctly needs no logging.
  - flood-risk entries (empty decision_classes, loop-nested log call) — these
    are raven-flood's territory; raven-decision-map itself says "never
    instrument these as ordinary decision points," so gating on them the same
    way would contradict the skill this gate is built on.

This is a fully deterministic, stdlib-only script — no LLM call — precisely
because a hard-blocking gate needs to be fast and reliable on every commit.
The richer, judgment-informed report (including "recommended" findings) is
generated separately by a real Claude session and stays advisory-only (see
the `claude -p` step in install-guardrail-pre-commit-hook.sh) — decoupled on
purpose so a slow/flaky LLM call can never be why a commit hangs or is
wrongly blocked/passed.

Scans every tracked file **in-process** via the scanner's own analyze_file()
(imported once), not one `python3 ast_decision_scanner.py --file X` subprocess
per file — measured at ~56s for 487 files on the per-subprocess approach
(interpreter startup dominates), which is real, avoidable latency a
synchronous pre-commit gate should never carry. This is the same in-process
import idiom guardrail-pipeline.py already uses for the same reason.

Baseline (PR #173 review, C1): a whole-repo hard gate with no baseline means
the very first time this runs against an existing codebase, it blocks EVERY
commit on however much pre-existing debt already exists — which for a real
repo of any size is every commit, forever, until that debt is fully cleared.
`.raven/decision-map-baseline.json` (committed, shared by the team) records
the findings a team has explicitly accepted as pre-existing; only findings
NOT in the baseline block a commit. This does not weaken the gate to
diff-only scanning — it still scans the whole repo every run, per this
file's own stated design — it only changes which of the whole-repo findings
are new enough to block. A finding's identity is (file, line, symbol): a
deliberately simple key, not a perfect one — an unrelated edit that shifts
line numbers elsewhere in the same file can make a genuinely unchanged
finding look "new" and re-trigger a block. That's a known, accepted tradeoff
of line-based baselines (the same one mypy's/other tools' baseline features
carry), not something this file tries to solve with fuzzier matching.

Every real run (pass or block, --write-baseline excluded) also renders a
findings HTML/JSON report — see build_report()/render_html()/write_report()
below — covering every entry the scanner produced, not just the ones that
block. `.raven/reports/decision-map-latest.{json,html}` always reflects the
most recent run; `.raven/reports/history/` keeps one immutable snapshot per
run (see write_report()'s docstring for why it's keyed by parent sha, not
the new commit's sha), capped at the most recent MAX_HISTORY.

Usage:
    python3 decision-map-gate.py                 # normal run — blocks on
                                                    non-baselined findings
    python3 decision-map-gate.py --write-baseline # accept every current
                                                    finding as baseline;
                                                    always exits 0

Exit codes: 0 = no blocking findings (or --write-baseline ran) | 1 = blocking
findings found (commit BLOCKED) | 2 never used — scanner-unavailable fails
OPEN (0), since a missing scanner is an environment gap, not evidence the
code is fine, but also not a reason to block an unrelated commit.
"""
import argparse
import html as html_lib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Windows' default console/pipe encoding (cp1252) can't encode the emoji used
# in this script's own output -- crashing what's designed to be advisory/
# fail-open output into a hard crash, and via `|| exit 1` in the pre-commit
# hook, a real block on every commit. errors="replace" guarantees this can
# never crash on any platform; worst case an emoji renders as a placeholder.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASELINE_PATH = Path(".raven") / "decision-map-baseline.json"
REPORTS_DIR = Path(".raven") / "reports"
HISTORY_DIR = REPORTS_DIR / "history"
HISTORY_INDEX_PATH = HISTORY_DIR / "index.json"
MAX_HISTORY = 50

# G28 (RAVEN-LOG-GAP-VALIDATION.md) — calibrated against the real 21->339
# (16x) jump this session hit fixing G-bonus-1's urllib blind spot: that
# incident crossed both an absolute and a relative threshold, so either one
# alone is sufficient to fire — a small repo can cross the relative
# threshold on a tiny absolute change, and a large repo can cross the
# absolute threshold on a small relative change.
JUMP_ABSOLUTE_THRESHOLD = 50
JUMP_RELATIVE_THRESHOLD = 0.5  # +50%


def find_scanner() -> Optional[Path]:
    """Project-local copy first (this repo builds the skill itself), then the
    user-level skill install (every other project that installs this hook)."""
    candidates = [
        Path("skills/raven-decision-map/scripts/ast_decision_scanner.py"),
        Path.home() / ".claude" / "skills" / "raven-decision-map" / "scripts" / "ast_decision_scanner.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def load_scanner(scanner_path: Path):
    spec = importlib.util.spec_from_file_location("ast_decision_scanner", scanner_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracked_python_files() -> Optional[list]:
    """Returns the tracked *.py file list, or None if `git ls-files` itself
    failed (not a git repo, corrupted git state, ...) — kept distinct from a
    genuinely empty list, so a real environment failure doesn't get reported
    as "no Python files, all clean" (PR #173 review, M1)."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "*.py"], stderr=subprocess.DEVNULL
        ).decode()
        return [f for f in out.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return None


def scan_file(scanner_module, file_path: str) -> list:
    """One file's placement-plan entries, in-process. Fails open per-file — a
    single unparseable file must not silently exempt the whole gate, but also
    must not crash it; analyze_file() already skips syntax errors per-file
    with a note printed to stdout, so an unexpected exception here would be a
    real bug in the scanner, not an expected outcome."""
    try:
        return [asdict(entry) for entry in scanner_module.analyze_file(file_path)]
    except Exception:
        return []


def collect_entries(scanner_module, files: list) -> list:
    """Every entry analyze_file() produces, across every file, unfiltered —
    the full-fidelity scan the report is built from. Scans each file exactly
    once; compute_blocking() below filters this same list rather than
    re-scanning, for the same avoid-double-AST-parse reason this file's
    module docstring already gives for scanning in-process at all."""
    entries = []
    for f in files:
        entries.extend(scan_file(scanner_module, f))
    return entries


def compute_blocking(entries: list) -> list:
    """The gate's own filter, now over an already-collected entry list
    instead of re-scanning files (previously scan_project() did both at
    once)."""
    blocking = []
    for entry in entries:
        status = entry.get("mandatory_status")
        if status not in ("mandatory", "recommended"):
            continue  # excludes "no-log" (explicit exemption)
        if not entry.get("decision_classes"):
            continue  # excludes flood-risk entries — raven-flood's territory, not this gate's
        if entry.get("existing_log_status") != "sufficient":
            blocking.append(entry)
    return blocking


def _finding_key(entry: dict):
    """Deliberately simple identity — see module docstring's "Baseline"
    section for the line-shift tradeoff this accepts."""
    return (entry.get("file"), entry.get("line"), entry.get("symbol"))


def load_baseline_entries(path: Path = BASELINE_PATH) -> list:
    """Full baseline entries with metadata (G19). Normalizes legacy bare
    [file, line, symbol] tuples (the ~1500 pre-existing entries from before this
    schema existed) into objects with outcome="accepted" and empty
    reason/reviewer/timestamp, so the old format never needs a bulk migration —
    both shapes are accepted forever. Never raises — same fail-open-on-availability
    posture load_baseline() already had."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for item in raw.get("findings", []):
        if isinstance(item, dict):
            out.append({
                "file": item.get("file"), "line": item.get("line"), "symbol": item.get("symbol"),
                "reason": item.get("reason", ""), "reviewer": item.get("reviewer", ""),
                "timestamp": item.get("timestamp", ""), "outcome": item.get("outcome", "accepted"),
            })
        else:
            # Legacy bare [file, line, symbol] tuple/list — pre-G19 baseline entry.
            try:
                file, line, symbol = item[0], item[1], item[2]
            except (IndexError, TypeError):
                continue
            out.append({"file": file, "line": line, "symbol": symbol,
                         "reason": "", "reviewer": "", "timestamp": "", "outcome": "accepted"})
    return out


def _load_rules():
    """raven-rules.py next to this script (all three roots) — the shared rule
    engine's shrink-only baseline helpers. None when missing: --write-baseline
    then behaves as it always did."""
    try:
        here = Path(__file__).resolve().parent / "raven-rules.py"
        if not here.exists():
            return None
        spec = importlib.util.spec_from_file_location("raven_rules", here)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # raven: expected advisory rule engine missing: the gate runs without its shrink-only guard
        return None


def _guard_baseline_write(blocking: list, allow_increase: bool, reason: str,
                          path: Path = BASELINE_PATH):
    """(ok, counts). Baselines only shrink (gap plan M2): counts per rule (or
    decision class) per top-level package may not grow unless
    --allow-increase and --reason are both given; raven-rules logs every
    accepted increase to .raven/baseline-increases.log. A baseline written
    before counts existed is compared through the findings it accepted."""
    rules = _load_rules()
    if rules is None:
        return True, None
    counts = rules.baseline_counts(blocking)
    if not path.exists():
        return True, counts  # the first baseline establishes the starting point
    try:
        stored = json.loads(path.read_text(encoding="utf-8")).get("counts")
    except Exception:  # raven: expected unreadable stored counts: compared through the accepted findings instead
        stored = None
    if not isinstance(stored, dict):
        accepted = load_baseline(path)
        stored = rules.baseline_counts([e for e in blocking if _finding_key(e) in accepted])
    ok, message = rules.guard_write("raven-decision-map-gate", stored, counts, allow_increase, reason)
    if message:
        print(("⚠️  " if ok else "❌ ") + message)
    return ok, counts


def load_baseline(path: Path = BASELINE_PATH) -> set:
    """Never raises — a missing or corrupt baseline file means "nothing is
    baselined yet," not a fatal error (fail-open on availability only; this
    is a convenience feature layered on top of the gate, not a replacement
    for it). Returns just the identity keys — the blocking check's call-site
    contract is unchanged by G19's richer entry schema."""
    return {_finding_key(e) for e in load_baseline_entries(path)}


def write_baseline(findings: list, path: Path = BASELINE_PATH,
                    reason: str = "", reviewer: str = "", outcome: str = "accepted",
                    counts: dict = None) -> int:
    """Findings no longer present this run are dropped (unchanged retirement-on-write
    behavior). Findings already in the baseline keep their PRIOR metadata untouched —
    re-running --write-baseline to accept a new batch of debt must never overwrite an
    earlier reviewer's reason/timestamp on unrelated, still-current entries (G19).
    Genuinely new findings get reason/reviewer/timestamp/outcome from this call."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {_finding_key(e): e for e in load_baseline_entries(path)}
    now = datetime.now(timezone.utc).isoformat()
    kept = {}
    for entry in findings:
        key = _finding_key(entry)
        if key in existing:
            kept[key] = existing[key]
        else:
            kept[key] = {
                "file": key[0], "line": key[1], "symbol": key[2],
                "reason": reason, "reviewer": reviewer, "timestamp": now, "outcome": outcome,
            }
    ordered = sorted(kept.values(), key=lambda e: (e["file"] or "", e["line"] or 0, e["symbol"] or ""))
    extra = {"counts": counts} if counts is not None else {}
    path.write_text(json.dumps({
        **extra,
        "note": "Findings accepted as pre-existing debt at the time each was baselined — "
                "raven-core/decision-map-gate.py only blocks on findings NOT in this list. "
                "Each entry's reason/reviewer/timestamp/outcome (G19) records WHY it was "
                "accepted, not just that it was. Regenerate with --write-baseline after "
                "deliberately accepting more debt — prior entries' metadata is preserved, "
                "not overwritten. Do not hand-edit to silence a real new finding.",
        "findings": ordered,
    }, indent=2) + "\n", encoding="utf-8")
    return len(ordered)


# ── Findings report (JSON + standalone HTML) ─────────────────────────────────
# Card/bucket semantics, confirmed against ast_decision_scanner.py:
#   - mandatory_status ("mandatory"/"recommended"/"diagnostic-only"/"no-log")
#     is a straight per-entry field — the stat cards are just a count of it
#     across every entry, not something this gate derives.
#   - governance_routing ("blocking_gate"/"standard_review"/"auto_pass") is
#     ALSO scanner-native (_route_for_governance: confidence + reversibility +
#     cost) — it is NOT this gate's own baseline mechanism. A "blocking_gate"
#     entry here is the scanner's risk-routing recommendation, independent of
#     whether it happens to already be baselined in this repo (that's what
#     compute_blocking()/the baseline file separately decide). The three gate
#     cards only cover entries with mandatory_status in (mandatory,
#     recommended) and a non-empty decision_classes — matching the reference
#     report, where the three cards summed to mandatory+recommended, not the
#     grand total.

_STATUS_ORDER = ["mandatory", "recommended", "diagnostic-only", "no-log"]
_STATUS_COLOR = {
    "mandatory": "#f87171",
    "recommended": "#f59e0b",
    "diagnostic-only": "#94a3b8",
    "no-log": "#cbd5e1",
}
_GATE_ORDER = ["blocking_gate", "standard_review", "auto_pass"]
_GATE_COLOR = {
    "blocking_gate": "#f87171",
    "standard_review": "#f59e0b",
    "auto_pass": "#4ade80",
}


def _ordered(counts: dict, preferred: list) -> list:
    ordered = [k for k in preferred if k in counts]
    ordered += sorted(k for k in counts if k not in preferred)
    return ordered


def _is_flood_risk(entry: dict) -> bool:
    """Same identity compute_blocking() uses to exclude these (empty decision_classes,
    loop-nested log call) — but here to surface them as their own visible category
    (G29) instead of just filtering them out silently. Checking mandatory_status ==
    "recommended" specifically (not "no-log") distinguishes a real flood-risk finding
    from an unrelated no-log exemption, which also has empty decision_classes."""
    return (
        not entry.get("decision_classes")
        and entry.get("mandatory_status") == "recommended"
        and bool(entry.get("related_rca_use_case"))
    )


def build_report(entries: list, files: list) -> dict:
    status_counts = Counter(e.get("mandatory_status") or "unknown" for e in entries)

    class_counts = Counter()
    for e in entries:
        for c in (e.get("decision_classes") or []):
            class_counts[c] += 1

    file_counts = Counter(e.get("file") for e in entries if e.get("file"))

    routable = [
        e for e in entries
        if e.get("mandatory_status") in ("mandatory", "recommended") and e.get("decision_classes")
    ]
    gate_counts = Counter(e.get("governance_routing") or "unrouted" for e in routable)

    # G29: flood-risk entries are correctly excluded from compute_blocking() (they're
    # raven-flood's territory, not this gate's) — but excluded from blocking and
    # invisible in the report look identical to a reader. Surface them separately.
    flood_risk_entries = [e for e in entries if _is_flood_risk(e)]
    flood_risk_file_counts = Counter(e.get("file") for e in flood_risk_entries if e.get("file"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(entries),
        "files_scanned": len(files),
        "files_with_findings": len(file_counts),
        "status_counts": dict(status_counts),
        "class_counts": dict(class_counts),
        "top_files": sorted(file_counts.items(), key=lambda kv: -kv[1])[:10],
        "gate_counts": dict(gate_counts),
        "flood_risk_count": len(flood_risk_entries),
        "flood_risk_top_files": sorted(flood_risk_file_counts.items(), key=lambda kv: -kv[1])[:10],
        "findings": [
            {
                "file": e.get("file"),
                "line": e.get("line"),
                "symbol": e.get("symbol"),
                "status": e.get("mandatory_status"),
                "classes": e.get("decision_classes") or [],
                "reason": e.get("reason"),
                "governance_routing": e.get("governance_routing"),
            }
            for e in entries
        ],
    }


def _bar_panel(title: str, counts: dict, order: Optional[list] = None, empty_note: str = "") -> str:
    keys = order if order else sorted(counts, key=lambda k: -counts.get(k, 0))
    keys = [k for k in keys if counts.get(k)]
    max_v = max(counts.values()) if counts else 0
    rows = []
    for k in keys:
        v = counts[k]
        pct = round(100 * v / max_v) if max_v else 0
        rows.append(
            f"<div class='bar-row'><span class='bar-label'>{html_lib.escape(str(k))}</span>"
            f"<span class='bar-track'><span class='bar-fill' style='width:{pct}%'></span></span>"
            f"<span class='bar-value'>{v}</span></div>"
        )
    body = "".join(rows) or "<p class='dim'>No entries.</p>"
    note = f"<p class='dim note'>{html_lib.escape(empty_note)}</p>" if empty_note else ""
    return f"<div class='tile'><h3>{html_lib.escape(title)}</h3>{body}{note}</div>"


def render_html(report: dict) -> str:
    status_counts = report.get("status_counts", {})
    gate_counts = report.get("gate_counts", {})
    class_counts = report.get("class_counts", {})
    top_files = dict(report.get("top_files", []))
    flood_risk_top_files = dict(report.get("flood_risk_top_files", []))
    findings = report.get("findings", [])

    stat_cards = [f"<div class='stat'><div class='stat-n'>{report.get('total', 0)}</div>"
                  f"<div class='stat-l'>TOTAL FINDINGS</div></div>"]
    for status in _ordered(status_counts, _STATUS_ORDER):
        color = _STATUS_COLOR.get(status, "#e2e8f0")
        stat_cards.append(
            f"<div class='stat'><div class='stat-n' style='color:{color}'>{status_counts[status]}</div>"
            f"<div class='stat-l'>{html_lib.escape(status.upper())}</div></div>"
        )
    stat_cards.append(
        f"<div class='stat'><div class='stat-n' style='color:#2dd4bf'>"
        f"{report.get('files_with_findings', 0)} / {report.get('files_scanned', 0)}</div>"
        f"<div class='stat-l'>FILES WITH FINDINGS</div></div>"
    )
    stat_cards.append(
        f"<div class='stat'><div class='stat-n' style='color:#38bdf8'>"
        f"{report.get('flood_risk_count', 0)}</div>"
        f"<div class='stat-l'>FLOOD-RISK (raven-flood territory, not blocking)</div></div>"
    )

    class_missing = ""
    if not class_counts:
        class_missing = "No decision-classified entries in this scan."
    class_panel = _bar_panel("FINDINGS BY DECISION CLASS", class_counts, empty_note=class_missing)

    files_missing = ""
    if not top_files:
        files_missing = "No files with findings — nothing to rank."
    files_panel = _bar_panel("TOP FILES BY FINDING COUNT", top_files, empty_note=files_missing)

    flood_missing = ""
    if not flood_risk_top_files:
        flood_missing = "No flood-risk findings — nothing to rank."
    flood_panel = _bar_panel("TOP FILES BY FLOOD-RISK FINDING COUNT", flood_risk_top_files, empty_note=flood_missing)

    gate_cards = []
    for gate in _ordered(gate_counts, _GATE_ORDER):
        color = _GATE_COLOR.get(gate, "#94a3b8")
        gate_cards.append(
            f"<div class='gate-card' style='border-left-color:{color}'>"
            f"<span>{html_lib.escape(gate)}</span><span class='gate-n'>{gate_counts[gate]}</span></div>"
        )
    gate_cards_html = "".join(gate_cards) or "<p class='dim'>No mandatory/recommended entries to route.</p>"

    pills = ["<button class='pill on' data-filter='all' onclick='filterStatus(this)'>"
             f"All {report.get('total', 0)}</button>"]
    for status in _ordered(status_counts, _STATUS_ORDER):
        pills.append(
            f"<button class='pill' data-filter='{html_lib.escape(status)}' onclick='filterStatus(this)'>"
            f"{html_lib.escape(status.title())} {status_counts[status]}</button>"
        )

    rows = []
    for f in findings:
        status = f.get("status") or "unknown"
        classes_html = "".join(
            f"<span class='tag'>{html_lib.escape(c)}</span>" for c in (f.get("classes") or [])
        )
        rows.append(
            "<tr data-status='%s'><td><span class='badge' style='color:%s;border-color:%s'>%s</span></td>"
            "<td><code>%s:%s</code></td><td><code>%s</code></td><td>%s</td><td class='dim'>%s</td></tr>"
            % (
                html_lib.escape(status),
                _STATUS_COLOR.get(status, "#e2e8f0"), _STATUS_COLOR.get(status, "#e2e8f0"),
                html_lib.escape(status.upper()),
                html_lib.escape(str(f.get("file") or "")), html_lib.escape(str(f.get("line") or "")),
                html_lib.escape(str(f.get("symbol") or "")),
                classes_html,
                html_lib.escape(str(f.get("reason") or "")),
            )
        )
    rows_html = "".join(rows) or "<tr><td colspan='5' class='dim'>No findings.</td></tr>"

    generated = html_lib.escape(report.get("generated_at", ""))

    jump_alert = report.get("jump_alert")
    jump_banner = ""
    if jump_alert:
        pct = f", {jump_alert['relative_pct']:.0f}%" if jump_alert.get("relative_pct") is not None else ""
        jump_banner = (
            "<div style='background:#451a03;border:1px solid #92400e;color:#fde68a;"
            "border-radius:8px;padding:12px 16px;margin:12px 0;font-size:13px;'>"
            f"⚠️ Un-baselined blocking findings jumped from <strong>{jump_alert['previous']}</strong> "
            f"to <strong>{jump_alert['current']}</strong> (+{jump_alert['delta']}{pct}) since the last run — "
            "review before accepting as baseline."
            "</div>"
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"/>
<title>Decision Map — findings report</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ background:#0b0f17; color:#e2e8f0; font:14px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif; margin:0; padding:24px; }}
  .wrap {{ max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:20px; margin:0 0 2px; }}
  .dim {{ color:#8b96a8; }}
  .note {{ margin-top:10px; }}
  .stats {{ display:flex; gap:12px; flex-wrap:wrap; margin:20px 0; }}
  .stat {{ flex:1; min-width:130px; background:#121826; border:1px solid #1f2937; border-radius:10px; padding:16px; }}
  .stat-n {{ font-size:28px; font-weight:700; }}
  .stat-l {{ font-size:11px; letter-spacing:.04em; color:#8b96a8; margin-top:4px; }}
  .panels {{ display:flex; gap:12px; flex-wrap:wrap; }}
  .tile {{ flex:1; min-width:340px; background:#121826; border:1px solid #1f2937; border-radius:10px; padding:16px; }}
  .tile h3 {{ font-size:12px; letter-spacing:.04em; color:#8b96a8; margin:0 0 14px; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin:10px 0; }}
  .bar-label {{ width:130px; flex-shrink:0; font-size:13px; }}
  .bar-track {{ flex:1; height:8px; background:#1f2937; border-radius:4px; overflow:hidden; }}
  .bar-fill {{ display:block; height:100%; background:#2dd4bf; border-radius:4px; }}
  .bar-value {{ width:32px; text-align:right; flex-shrink:0; }}
  .gate-cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:12px 0 20px; }}
  .gate-card {{ flex:1; min-width:180px; background:#121826; border:1px solid #1f2937; border-left:4px solid; border-radius:8px; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; }}
  .gate-n {{ font-size:18px; font-weight:700; }}
  .findings {{ background:#121826; border:1px solid #1f2937; border-radius:10px; padding:16px; margin-top:4px; }}
  .findings-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px; }}
  .findings-head > span:first-child {{ font-size:11px; letter-spacing:.04em; color:#8b96a8; }}
  .pills {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .pill {{ background:transparent; border:1px solid #1f2937; color:#8b96a8; border-radius:999px; padding:5px 12px; font-size:12px; cursor:pointer; }}
  .pill.on {{ background:#2dd4bf; border-color:#2dd4bf; color:#0b0f17; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; font-size:11px; letter-spacing:.04em; color:#8b96a8; padding:8px 10px; border-bottom:1px solid #1f2937; }}
  td {{ padding:10px; border-bottom:1px solid #1a2130; vertical-align:top; font-size:13px; }}
  code {{ color:#c9d6e8; }}
  .badge {{ border:1px solid; border-radius:999px; padding:2px 10px; font-size:11px; font-weight:600; }}
  .tag {{ display:inline-block; border:1px solid #14532d; background:rgba(45,212,191,.12); color:#5eead4; border-radius:999px; padding:1px 8px; font-size:11px; margin:0 4px 4px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Decision Map — findings report</h1>
  <p class="dim">Generated {generated} · {report.get('files_scanned', 0)} file(s) scanned</p>
  {jump_banner}
  <div class="stats">{''.join(stat_cards)}</div>
  <div class="panels">{class_panel}{files_panel}{flood_panel}</div>
  <div class="gate-cards">{gate_cards_html}</div>
  <div class="findings">
    <div class="findings-head">
      <span>ALL {report.get('total', 0)} FINDINGS</span>
      <span class="pills">{''.join(pills)}</span>
    </div>
    <table>
      <thead><tr><th>STATUS</th><th>FILE:LINE</th><th>SYMBOL</th><th>CLASS(ES)</th><th>REASON</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
<script>
function filterStatus(btn) {{
  var f = btn.dataset.filter;
  document.querySelectorAll('.pill').forEach(function(p) {{ p.classList.toggle('on', p === btn); }});
  document.querySelectorAll('tbody tr').forEach(function(r) {{
    r.style.display = (f === 'all' || r.dataset.status === f) ? '' : 'none';
  }});
}}
</script>
</body></html>
"""


def _git_parent_sha() -> str:
    """The commit this new commit will land on — the closest stable identity
    available at PRE-commit time (the new commit's own sha doesn't exist yet
    when this hook runs). "unborn" covers the first-ever commit in a repo,
    where HEAD has no parent."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
        return out[:12] if out else "unborn"
    except Exception:
        return "unborn"


def _load_history_index() -> list:
    try:
        raw = json.loads(HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _detect_finding_count_jump(current: int, history: list) -> Optional[dict]:
    """G28 — compare `current` (this run's un-baselined blocking count)
    against the most recent PRIOR history entry that actually has a
    `new_blocking_count` field. Older entries predating this field are
    skipped, not treated as "no prior data == 0" (that would misfire a jump
    alert on the very first run after this feature ships). Only an INCREASE
    is ever flagged — a drop in findings is good news, never an alert.

    A `previous` of 0 skips the relative check (any increase from zero is a
    mathematically infinite percentage, which is not a meaningful signal on
    its own) and relies on the absolute threshold alone."""
    for entry in reversed(history):
        previous = entry.get("new_blocking_count")
        if previous is None:
            continue
        delta = current - previous
        if delta <= 0:
            return None
        relative = (delta / previous) if previous > 0 else None
        if delta >= JUMP_ABSOLUTE_THRESHOLD or (relative is not None and relative >= JUMP_RELATIVE_THRESHOLD):
            return {
                "previous": previous,
                "current": current,
                "delta": delta,
                "relative_pct": round(relative * 100, 1) if relative is not None else None,
            }
        return None
    return None


def _write_history_snapshot(report: dict, html_doc: str) -> None:
    """One immutable snapshot per gate run — in practice, one per commit
    attempt (blocked attempts keep their record; the eventual successful
    commit gets the next one). Keyed by parent-sha + microsecond timestamp,
    not the new commit's sha (see _git_parent_sha's docstring). Caps
    retention at MAX_HISTORY snapshot pairs, pruning both the index entry and
    its files — never raises, this is a convenience layered on top of the
    always-current -latest pair, not something the gate depends on."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    parent = _git_parent_sha()
    stem = f"{parent}_{ts}"
    (HISTORY_DIR / f"{stem}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (HISTORY_DIR / f"{stem}.html").write_text(html_doc, encoding="utf-8")

    index = _load_history_index()
    index.append({
        "id": stem,
        "parent_sha": parent,
        "timestamp": ts,
        "total": report.get("total", 0),
        "gate_counts": report.get("gate_counts", {}),
        # G28 — the un-baselined blocking count, not `total` (every scan
        # entry including no-log ones). This is what a real jump alert needs
        # to compare against; absent from history entries written before
        # this field existed, which _detect_finding_count_jump() skips.
        "new_blocking_count": report.get("new_blocking_count"),
        "html": f"history/{stem}.html",
        "json": f"history/{stem}.json",
    })
    while len(index) > MAX_HISTORY:
        dropped = index.pop(0)
        for suffix in (".json", ".html"):
            try:
                (HISTORY_DIR / f"{dropped.get('id', '')}{suffix}").unlink(missing_ok=True)
            except Exception:
                pass
    HISTORY_INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


def write_report(report: dict) -> Optional[Path]:
    """Writes the always-current -latest pair plus a history snapshot. Wrapped
    so a disk/permission failure can never crash or block the gate — same
    fail-open posture as the rest of this file. Returns the -latest HTML path
    on success, None on any failure (callers must treat that as "no report
    this run," not an error)."""
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        html_doc = render_html(report)
        (REPORTS_DIR / "decision-map-latest.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        latest_html = REPORTS_DIR / "decision-map-latest.html"
        latest_html.write_text(html_doc, encoding="utf-8")
        _write_history_snapshot(report, html_doc)
        return latest_html
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Raven Decision-Map Gate")
    parser.add_argument("--write-baseline", action="store_true",
                        help="Accept every current finding as baseline (always exits 0)")
    parser.add_argument("--reason", default="",
                        help="G19: why NEW findings in this --write-baseline run are accepted debt")
    parser.add_argument("--reviewer", default="",
                        help="G19: who reviewed the NEW findings in this --write-baseline run")
    parser.add_argument("--allow-increase", action="store_true",
                        help="M2: let --write-baseline accept MORE findings per rule/package than "
                             "the last baseline (requires --reason; logged)")
    parser.add_argument("--outcome", default="accepted",
                        choices=["accepted", "false_positive", "deferred"],
                        help="G19: review outcome for NEW findings in this --write-baseline run")
    args = parser.parse_args()

    scanner = find_scanner()
    if scanner is None:
        print("⚠️  raven-decision-map-gate: scanner not found (not installed in this project's "
              "skills/raven-decision-map/ or ~/.claude/skills/) — skipping (fail-open, an "
              "environment gap is not evidence the code itself is fine, but also not a reason "
              "to block an unrelated commit)")
        return 0

    files = tracked_python_files()
    if files is None:
        print("⚠️  raven-decision-map-gate: 'git ls-files' failed — skipping (fail-open, "
              "an environment gap is not evidence the code itself is fine, but also not "
              "a reason to block an unrelated commit)")
        return 0
    if not files:
        print("✅ raven-decision-map-gate: no tracked Python files")
        return 0

    scanner_module = load_scanner(scanner)
    entries = collect_entries(scanner_module, files)
    blocking = compute_blocking(entries)

    if args.write_baseline:
        ok, counts = _guard_baseline_write(blocking, args.allow_increase, args.reason)
        if not ok:
            return 1
        count = write_baseline(blocking, reason=args.reason, reviewer=args.reviewer,
                               outcome=args.outcome, counts=counts)
        print(f"✅ raven-decision-map-gate: wrote {count} finding(s) to {BASELINE_PATH} "
              f"as the accepted baseline")
        return 0

    baseline = load_baseline()
    new_blocking = [e for e in blocking if _finding_key(e) not in baseline]
    baselined_count = len(blocking) - len(new_blocking)

    # G28: load history and detect a jump BEFORE this run's own snapshot is
    # written below — comparing against prior runs only, never against
    # itself.
    jump_alert = _detect_finding_count_jump(len(new_blocking), _load_history_index())

    report = build_report(entries, files)
    report["new_blocking_count"] = len(new_blocking)
    report["jump_alert"] = jump_alert
    report_path = write_report(report)

    flood_risk_count = report.get("flood_risk_count", 0)
    if flood_risk_count:
        print(f"🌊 raven-decision-map-gate: {flood_risk_count} flood-risk finding(s) "
              f"(loop-nested log calls) — raven-flood's territory, not blocking, see report")

    if jump_alert:
        print(f"⚠️  raven-decision-map-gate: un-baselined blocking findings jumped from "
              f"{jump_alert['previous']} to {jump_alert['current']} (+{jump_alert['delta']}"
              + (f", {jump_alert['relative_pct']:.0f}%" if jump_alert['relative_pct'] is not None else "")
              + ") since the last run — if this is real new debt, review it and "
              "--write-baseline with --reason; if it's a scanner/ruleset change, "
              "investigate why so many findings changed at once before accepting it")

    if not new_blocking:
        if baselined_count:
            print(f"✅ raven-decision-map-gate: {len(files)} file(s) scanned across the project — "
                  f"no unresolved NEW findings ({baselined_count} pre-existing, baselined, not blocking)")
        else:
            print(f"✅ raven-decision-map-gate: {len(files)} file(s) scanned across the project — "
                  f"no unresolved findings")
        if report_path:
            print(f"📄 Findings report: file://{report_path.resolve()}")
        return 0

    print(f"❌ raven-decision-map-gate: {len(new_blocking)} new finding(s) across the project "
          f"lack sufficient raven_log() evidence — commit BLOCKED")
    if baselined_count:
        print(f"   ({baselined_count} additional finding(s) are pre-existing and baselined — not blocking)")
    for entry in new_blocking:
        classes = ", ".join(entry.get("decision_classes") or [])
        status = entry.get("mandatory_status")
        print(f"   ❌ [{status}] {entry.get('file')}:{entry.get('line')} {entry.get('symbol')}() "
              f"[{classes}] — {entry.get('reason')}")
    print("   Add raven_log() calls per raven-log's schema (see /raven-log instrument), "
          "resolve why existing_log_status isn't 'sufficient' for these, or if this debt "
          "is deliberately accepted, run --write-baseline.")
    if report_path:
        print(f"📄 Full findings report: file://{report_path.resolve()}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"⚠️  raven-decision-map-gate: unexpected error — {e} (fail-open)")
        sys.exit(0)
