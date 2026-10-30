#!/usr/bin/env python3
"""
Raven — API-log middleware commit-time gate (mandatory http boundary records).

A separate, small, additive script — NOT a modification to raven-emitter-gate.py
(that file answers "does raven_log() reach a sink"; this one answers a different
question, "does every HTTP request produce an http boundary record"). Chained as one
more step in install-guardrail-pre-commit-hook.sh's generated hook body, same
pattern as secret-scan.py / guardrail-scan-gate.py / decision-map-gate.py /
raven-emitter-gate.py already are.

Why this gate exists at all: http boundary coverage is mandatory, and the only way to
make it mandatory rather than aspirational is to check a fact that cannot be
satisfied by accident. Per-route logging cannot be gated usefully — the best a
scanner could say is "some raven_log() call exists in this function", which does
not establish that the HTTP facts were recorded. Registering one middleware is a
single, checkable fact, so that is what this gate checks.

Hard-blocks (exit 1) on one check, same baseline mechanism decision-map-gate.py
and raven-emitter-gate.py already use (.raven/api-log-gate-baseline.json — a
repo that already defines ASGI apps in tests and tools would otherwise get
flooded on this gate's very first run):

  a tracked *.py file constructs an ASGI application (FastAPI(...)/Starlette(...))
  and does not register the API-log middleware on it.

Deliberately NOT flagged:
  - Files that only import FastAPI (e.g. for APIRouter or type hints) — the
    finding keys off app *construction*, not import.
  - APIRouter() — a router is mounted onto an app that is gated separately;
    requiring middleware on a router is not even expressible.
  - Test/fixture apps — excluded by directory, same exclusion list as its
    sibling gates. A test that builds a throwaway FastAPI() to exercise one
    route is not a service with an unlogged API surface.

KNOWN GAPS, stated plainly rather than implied by a docstring that promised
more than the check does (PR #563 review):

  - This is a per-FILE, name-MENTION heuristic, not a per-app data-flow
    analysis. A module that constructs N apps and mentions ApiLogMiddleware
    (as a bare Name or an `x.ApiLogMiddleware` Attribute) at least N times
    passes — e.g. two apps and two `add_middleware(ApiLogMiddleware, ...)`
    calls, even if a careless edit applied both to the same app and left the
    other bare. This catches the common "two apps, only one registered" case
    without the cost (and new-bug risk) of real per-variable data-flow
    tracking, but it is a proxy, not a proof.
  - A helper function that calls `add_middleware(ApiLogMiddleware, ...)` and
    is DEFINED IN ANOTHER MODULE will not be seen: this scanner reads one
    file's AST at a time. `install_raven_middleware(app)` called from the
    app-building file satisfies this gate ONLY if the literal name
    `ApiLogMiddleware` also appears somewhere in THAT file (e.g. imported, or
    passed to the helper by name: `install_raven_middleware(app,
    ApiLogMiddleware)`) — a helper that hides the class entirely inside
    another module is invisible here and the file will be (correctly, per
    what this scanner can actually see) blocked.

Fail-open on missing git or any internal error. Exit codes: 0 = clean/fail-open |
1 = blocking findings.

Usage:
    python3 raven-api-log-gate.py                   # whole tracked repo
    python3 raven-api-log-gate.py --write-baseline  # accept current findings
"""

import argparse
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path(".raven") / "api-log-gate-baseline.json"

# Class names whose construction creates an ASGI application with its own
# middleware stack. A sub-application mounted under another app still needs its
# own registration — Starlette does not run the parent's middleware for a
# mounted child's requests.
ASGI_APP_FACTORIES = {"FastAPI", "Starlette"}

# The middleware that satisfies this gate. Matched by name so a project is free
# to import it from wherever it keeps its middleware package.
API_LOG_MIDDLEWARE = "ApiLogMiddleware"

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


def _count_asgi_app_constructions(tree: ast.Module) -> int:
    """How many times this module calls FastAPI(...) or Starlette(...) — i.e.
    constructs an app with its own middleware stack, rather than merely
    referencing the class for a type hint or an APIRouter."""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in ASGI_APP_FACTORIES:
            count += 1
    return count


def _constructs_asgi_app(tree: ast.Module) -> bool:
    """True when this module constructs at least one ASGI app. See
    _count_asgi_app_constructions — scan() uses the count directly so that a
    module building more than one app needs more than one registration
    mention; this boolean form exists for callers (and tests) that only need
    the yes/no answer."""
    return _count_asgi_app_constructions(tree) > 0


def _count_api_log_middleware_mentions(tree: ast.Module) -> int:
    """How many times the literal name ApiLogMiddleware appears in this
    module, as a bare Name (`add_middleware(ApiLogMiddleware, ...)`) or an
    Attribute (`add_middleware(api_log.ApiLogMiddleware, ...)`).

    Matches the name in any call argument rather than insisting on the exact
    `app.add_middleware(ApiLogMiddleware, ...)` shape: a project may build its
    middleware list declaratively via `Middleware(ApiLogMiddleware, ...)`, or
    import-then-pass the class into a local helper, and those genuinely
    satisfy the requirement. See this file's module docstring ("KNOWN GAPS")
    for what this heuristic does and does not catch: it is a per-file mention
    count used as a proxy for "one registration per app in this file", not a
    per-variable data-flow proof, and it cannot see a helper function defined
    in a DIFFERENT module that never mentions the class by name in this one.
    """
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == API_LOG_MIDDLEWARE:
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == API_LOG_MIDDLEWARE:
            count += 1
    return count


def _registers_api_log_middleware(tree: ast.Module) -> bool:
    """True when ApiLogMiddleware is mentioned at least once anywhere in the
    module. Boolean form of _count_api_log_middleware_mentions, for callers
    (and tests) that only need the yes/no answer — scan() itself uses the
    count, so a module with two app constructions needs two mentions, not
    just one."""
    return _count_api_log_middleware_mentions(tree) > 0


# ── Non-HTTP entry points (gap plan M3) ───────────────────────────────────────
# HTTP was the only entry point this gate could see; an MCP server, a Celery
# worker or a queue consumer could ship with no boundary record at all. Each
# needs raven-instrument.py's matching adapter: mcp_audit() for an official-
# SDK MCP server, a job boundary (@inst.job() or boundary("job", ...)) per
# Celery task, a queue boundary (@inst.consumer(...) or boundary("queue", ...))
# where a file consumes messages. Same per-file, count-based heuristic as the
# HTTP check above, with the same "KNOWN GAPS".
MCP_SERVER_FACTORIES = {"FastMCP"}
MCP_SERVER_MODULE_PREFIX = "mcp.server"         # `Server` counts only when imported from here
TASK_DECORATORS = {"task", "shared_task"}       # Celery's @app.task / @shared_task (and look-alikes)
CONSUMER_METHODS = {"receive_message", "basic_consume", "start_consuming"}
CONSUMER_FACTORIES = {"KafkaConsumer", "AIOKafkaConsumer", "Consumer"}
CONSUMER_MODULES = ("kafka", "confluent_kafka", "aiokafka")


def _imported_from(tree: ast.Module, prefixes) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and \
                any(node.module == p or node.module.startswith(p + ".") for p in prefixes):
            names.update(a.asname or a.name for a in node.names)
    return names


def _mentions(tree: ast.Module, names) -> int:
    return sum(1 for node in ast.walk(tree)
               if (isinstance(node, ast.Name) and node.id in names)
               or (isinstance(node, ast.Attribute) and node.attr in names))


def _boundary_kind_calls(tree: ast.Module, kind: str) -> int:
    """Calls like inst.boundary("job", ...)."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) == "boundary":
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and first.value == kind:
                count += 1
    return count


def _decorator_name(dec) -> str:
    target = dec.func if isinstance(dec, ast.Call) else dec
    return getattr(target, "attr", None) or getattr(target, "id", None) or ""


def _entry_point_findings(tree: ast.Module) -> list:
    """Finding kinds for this module's non-HTTP entry points left unwrapped."""
    found = []
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    called = [getattr(c.func, "id", None) or getattr(c.func, "attr", None) for c in calls]

    lowlevel = _imported_from(tree, [MCP_SERVER_MODULE_PREFIX]) & {"Server"}
    mcp_servers = sum(1 for name in called if name in MCP_SERVER_FACTORIES or name in lowlevel)
    if mcp_servers and _mentions(tree, {"mcp_audit"}) < mcp_servers:
        found.append("missing-mcp-audit")

    # Task decorators count wherever the Celery app itself is built: tasks
    # usually live in other modules than `Celery(...)`.
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [_decorator_name(d) for d in func.decorator_list]
        if not set(decorators) & TASK_DECORATORS:
            continue
        if not ("job" in decorators or _boundary_kind_calls(func, "job")):
            found.append("missing-job-boundary")
            break

    consumer_factories = _imported_from(tree, CONSUMER_MODULES) & CONSUMER_FACTORIES
    consumes = any(name in CONSUMER_METHODS for name in called) or \
        any(name in consumer_factories for name in called)
    if consumes and not (_mentions(tree, {"consumer"}) or _boundary_kind_calls(tree, "queue")):
        found.append("missing-consumer-boundary")
    return found


def findings_for_tree(tree: ast.Module) -> list:
    """Every finding kind for one parsed module — HTTP and non-HTTP. scan()
    and logging-doctor.py share it so they can't disagree."""
    kinds = []
    constructions = _count_asgi_app_constructions(tree)
    if constructions and _count_api_log_middleware_mentions(tree) < constructions:
        kinds.append("missing-api-log-middleware")
    return kinds + _entry_point_findings(tree)


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
                "written — raven-api-log-gate.py only blocks on findings NOT in this "
                "list. Regenerate with --write-baseline after deliberately accepting "
                "more debt.",
        "findings": [list(k) for k in keys],
    }, indent=2) + "\n", encoding="utf-8")
    return len(keys)


def scan(root: Path) -> tuple:
    """Returns (findings, files_scanned), where each finding is a
    ("missing-api-log-middleware", file) pair."""
    files = [f for f in _tracked_py_files() if _is_scoped(Path(f), root)]
    findings = []
    for f in files:
        path = root / f
        text = _safe(lambda: path.read_text(encoding="utf-8", errors="replace"))
        if text is None:
            continue
        tree = _safe(lambda: ast.parse(text, filename=f))
        if tree is None:
            continue
        # Count, not boolean-AND: a module constructing 2 apps needs 2
        # mentions of ApiLogMiddleware, not just 1 — see "KNOWN GAPS" above
        # for what this heuristic does and does not prove.
        findings.extend((kind, f) for kind in findings_for_tree(tree))
    return findings, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Raven API-log middleware gate")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--allow-increase", action="store_true",
                        help="Let --write-baseline accept MORE findings than the last baseline (needs --reason)")
    parser.add_argument("--reason", default="", help="Why the baseline is allowed to grow (logged)")
    args = parser.parse_args()

    root = Path.cwd().resolve()
    findings, scanned = scan(root)
    if not scanned:
        print("✅ raven-api-log-gate: no in-scope Python files")
        return 0

    if args.write_baseline:
        ok, counts = _guard_baseline_write("raven-api-log-gate", findings, BASELINE_PATH,
                                           args.allow_increase, args.reason)
        if not ok:
            return 1
        count = _write_baseline(findings, counts=counts)
        print(f"✅ raven-api-log-gate: wrote {count} finding(s) to {BASELINE_PATH} as the accepted baseline")
        return 0

    baseline = _load_baseline()
    new_findings = [f for f in findings if f not in baseline]
    baselined_count = len(findings) - len(new_findings)

    if not new_findings:
        if baselined_count:
            print(f"✅ raven-api-log-gate: {scanned} file(s) scanned — no unresolved NEW "
                  f"findings ({baselined_count} pre-existing, baselined, not blocking)")
        else:
            print(f"✅ raven-api-log-gate: {scanned} file(s) scanned — no unresolved findings")
        return 0

    print(f"❌ raven-api-log-gate: {len(new_findings)} new finding(s) — commit BLOCKED")
    for kind, f in new_findings:
        what, fix = FINDING_MESSAGES.get(kind, (kind, ""))
        print(f"   ❌ {f}: {what}")
        if fix:
            print(f"      fix: {fix}")
    print("   If this debt is deliberately accepted, run --write-baseline "
          "(baselines only shrink: growth needs --allow-increase --reason).")
    return 1


FINDING_MESSAGES = {
    "missing-api-log-middleware": (
        f"constructs an ASGI app without registering {API_LOG_MIDDLEWARE} — every HTTP request "
        f"must emit an http boundary record",
        "add it as the LAST add_middleware() call: "
        "app.add_middleware(ApiLogMiddleware, service=..., env=..., project=...)"),
    "missing-mcp-audit": (
        "builds an MCP server without mcp_audit() — every tool call must emit an mcp boundary record",
        "inst.mcp_audit(server) right after creating it (raven-instrument.py)"),
    "missing-job-boundary": (
        "defines a task with no job boundary — every run must emit a job boundary record",
        "decorate it with @inst.job() under the task decorator, or wrap its body in "
        "inst.boundary(\"job\", ...)"),
    "missing-consumer-boundary": (
        "consumes queue messages with no queue boundary — every message must emit a queue "
        "boundary record",
        "decorate the per-message handler with @inst.consumer(\"<queue>\") or wrap it in "
        "inst.boundary(\"queue\", ...)"),
}


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"⚠️  raven-api-log-gate: unexpected error — {e} (fail-open)")
        sys.exit(0)
