#!/usr/bin/env python3
"""
Raven — emitter-wiring commit-time gate (design.md / RAVEN-LOG-ENFORCEMENT-PLAN.md).

A separate, small, additive script — NOT a modification to decision-map-gate.py (that
file already has its own tests and its own single responsibility, "does a mandatory
decision point have sufficient raven_log() evidence"; emitter wiring is a different
question, "does raven_log() actually reach anywhere"). Chained as one more step in
install-guardrail-pre-commit-hook.sh's generated hook body, same pattern as
secret-scan.py / guardrail-scan-gate.py / decision-map-gate.py already are.

Hard-blocks (exit 1) on two checks, same baseline mechanism decision-map-gate.py already
uses (.raven/emitter-gate-baseline.json — a repo of this size, 600+ pre-existing Python
files including two that already import raven_logger directly, would otherwise get
flooded on this gate's very first run):

  (a) any tracked *.py file (outside .claude/raven-core/agent/skills/plugin/tests/vendor
      dirs) imports raven_log directly from raven_logger instead of via config.py's
      log() wrapper — config.py itself is exempt, it's the one correct place for this;
  (b) at least one such file uses the config.py wrapper or imports raven_logger at all,
      but repo-root config.py has no constructed S3Emitter + log() wrapper.

Fail-open on missing git or any internal error. Exit codes: 0 = clean/fail-open |
1 = blocking findings.

Usage:
    python3 raven-emitter-gate.py                  # whole tracked repo (like decision-map-gate.py)
    python3 raven-emitter-gate.py --write-baseline  # accept current findings as baseline
"""

import argparse
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path(".raven") / "emitter-gate-baseline.json"

# config.py (repo root) is the one correct place to import raven_logger
# directly -- everything else must go through its log() wrapper. Scanning it
# for a "direct-import" finding would block the very file this gate exists
# to make sure everyone else uses.
CONFIG_PY_EXEMPT = "config.py"

EXCLUDE_DIR_PARTS = {
    ".claude", ".git", ".raven", "raven-core", "agent", "skills", "plugin", "tests",
    "examples", "raven-guardrail-package",
    "node_modules", ".venv", "venv", "dist", "build", "site-packages", "__pycache__",
}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _is_scoped(path: Path, root: Path) -> bool:
    if path.suffix != ".py":
        return False
    try:
        rel_parts = set(path.resolve().relative_to(root).parts)
    except ValueError:
        return False
    return not (EXCLUDE_DIR_PARTS & rel_parts)


def _tracked_py_files() -> list:
    try:
        out = subprocess.check_output(["git", "ls-files", "*.py"], stderr=subprocess.DEVNULL).decode()
        return [f for f in out.splitlines() if f.strip()]
    except Exception:
        return []


def _imports_config(node) -> bool:
    if isinstance(node, ast.ImportFrom) and node.module == "config":
        return True
    return isinstance(node, ast.Import) and any((a.name or "") == "config" for a in node.names)


def _guarded_fallback_imports(tree: ast.Module) -> set:
    """ids of import nodes inside the except branch of a try whose body
    imports config: the wrapper-first, SDK-only-if-config-is-missing shape
    (hub/app/services/raven_log_shim.py). That import can't bypass the
    wrapper — it only runs when there is no wrapper to use."""
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_imports_config(n) for stmt in node.body for n in ast.walk(stmt)):
            continue
        for handler in node.handlers:
            for n in ast.walk(handler):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    guarded.add(id(n))
    return guarded


def _direct_sdk_import(tree: ast.Module) -> bool:
    guarded = _guarded_fallback_imports(tree)
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "raven_logger":
            if any((a.asname or a.name) == "raven_log" for a in node.names):
                return True
        if isinstance(node, ast.Import):
            if any((a.name or "").split(".")[0] == "raven_logger" for a in node.names):
                return True
    return False


def _uses_config_wrapper(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "config":
            if any(a.name == "log" for a in node.names):
                return True
        if isinstance(node, ast.Import) and any((a.name or "") == "config" for a in node.names):
            return True
    return False


def _emitter_configured(root: Path) -> bool:
    config_path = root / "config.py"
    if not config_path.exists():
        return False
    text = _safe(lambda: config_path.read_text(encoding="utf-8"), "")
    return "S3Emitter(" in text and "def log(" in text


def _load_baseline(path: Path = BASELINE_PATH) -> set:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {tuple(item) for item in raw.get("findings", [])}
    except Exception:
        return set()


def _load_rules():
    """raven-rules.py (next to this script) for the shrink-only baseline
    write; None when it's missing, which leaves --write-baseline as it was."""
    try:
        here = Path(__file__).resolve().parent / "raven-rules.py"
        if not here.exists():
            return None
        spec = importlib.util.spec_from_file_location("raven_rules", here)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # raven: expected unparseable source is skipped, as the other gates do (fail-open)
        return None


def _stored_counts(path: Path):
    try:
        counts = json.loads(path.read_text(encoding="utf-8")).get("counts")
        return counts if isinstance(counts, dict) else None
    except Exception:  # raven: expected unparseable source is skipped, as the other gates do (fail-open)
        return None


def _guard_baseline_write(gate: str, findings: list, path: Path, allow_increase: bool, reason: str):
    """(ok, counts). Baselines only shrink (gap plan M2): a write that raises
    any per-kind, per-package count is refused unless --allow-increase and
    --reason are both given; an accepted increase is logged by raven-rules."""
    rules = _load_rules()
    if rules is None:
        return True, None
    entries = [{"kind": kind, "file": file} for kind, file in findings]
    if not path.exists():
        return True, rules.baseline_counts(entries)  # the first baseline is the starting point
    accepted = _load_baseline(path)
    old = _stored_counts(path)
    if old is None:
        old = rules.baseline_counts([e for e, f in zip(entries, findings) if tuple(f) in accepted])
    new = rules.baseline_counts(entries)
    ok, message = rules.guard_write(gate, old, new, allow_increase, reason)
    if message:
        print(("⚠️  " if ok else "❌ ") + message)
    return ok, new


def _write_baseline(findings: list, path: Path = BASELINE_PATH, counts: dict = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({tuple(f) for f in findings})
    extra = {"counts": counts} if counts is not None else {}
    path.write_text(json.dumps({**extra, 
        "note": "Findings accepted as pre-existing debt at the time this baseline was "
                "written — raven-emitter-gate.py only blocks on findings NOT in this "
                "list. Regenerate with --write-baseline after deliberately accepting "
                "more debt.",
        "findings": [list(k) for k in keys],
    }, indent=2) + "\n", encoding="utf-8")
    return len(keys)


def main() -> int:
    parser = argparse.ArgumentParser(description="Raven emitter-wiring gate")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--allow-increase", action="store_true",
                        help="Let --write-baseline accept MORE findings than the last baseline (needs --reason)")
    parser.add_argument("--reason", default="", help="Why the baseline is allowed to grow (logged)")
    args = parser.parse_args()

    root = Path.cwd().resolve()
    files = [f for f in _tracked_py_files() if _is_scoped(Path(f), root)]
    if not files:
        print("✅ raven-emitter-gate: no in-scope Python files")
        return 0

    emitter_ok = _emitter_configured(root)
    any_raven_logger_usage = False
    findings = []  # list of ("direct-import", file) or ("emitter-not-configured", file)

    for f in files:
        if f == CONFIG_PY_EXEMPT:
            continue
        path = root / f
        text = _safe(lambda: path.read_text(encoding="utf-8", errors="replace"))
        if text is None:
            continue
        tree = _safe(lambda: ast.parse(text, filename=f))
        if tree is None:
            continue

        uses_wrapper = _uses_config_wrapper(tree)
        direct_import = _direct_sdk_import(tree)
        if uses_wrapper or direct_import:
            any_raven_logger_usage = True

        if direct_import:
            findings.append(("direct-import", f))
        if uses_wrapper and not emitter_ok:
            findings.append(("emitter-not-configured", f))

    if any_raven_logger_usage and not emitter_ok and not any(k == "emitter-not-configured" for k, _ in findings):
        findings.append(("emitter-not-configured", "config.py"))

    if args.write_baseline:
        ok, counts = _guard_baseline_write("raven-emitter-gate", findings, BASELINE_PATH,
                                           args.allow_increase, args.reason)
        if not ok:
            return 1
        count = _write_baseline(findings, counts=counts)
        print(f"✅ raven-emitter-gate: wrote {count} finding(s) to {BASELINE_PATH} as the accepted baseline")
        return 0

    baseline = _load_baseline()
    new_findings = [f for f in findings if f not in baseline]
    baselined_count = len(findings) - len(new_findings)

    if not new_findings:
        if baselined_count:
            print(f"✅ raven-emitter-gate: {len(files)} file(s) scanned — no unresolved NEW "
                  f"findings ({baselined_count} pre-existing, baselined, not blocking)")
        else:
            print(f"✅ raven-emitter-gate: {len(files)} file(s) scanned — no unresolved findings")
        return 0

    print(f"❌ raven-emitter-gate: {len(new_findings)} new finding(s) — commit BLOCKED")
    for kind, f in new_findings:
        if kind == "direct-import":
            print(f"   ❌ {f}: imports raven_log directly from raven_logger — "
                  f"use `from config import log as raven_log` instead")
        else:
            print(f"   ❌ {f}: uses raven_logger but config.py has no S3Emitter configured")
    print("   If this debt is deliberately accepted, run --write-baseline.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"⚠️  raven-emitter-gate: unexpected error — {e} (fail-open)")
        sys.exit(0)
