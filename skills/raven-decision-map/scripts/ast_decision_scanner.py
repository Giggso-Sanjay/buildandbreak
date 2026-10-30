#!/usr/bin/env python3
"""
Raven — AST Decision-Point Scanner v1.0
Deterministic, structure-based detection of the seven decision classes
(Routing, Policy or Guard, Eligibility, State Transition, Dependency,
Recovery, Outcome) and production of a machine-readable placement plan.

This is the canonical detection engine behind raven-decision-map. It is a
different tool from raven-log/raven-applog's log-coverage-check.py, which
stays a lightweight pass/fail percentage counter for CI. This script answers
a richer question per candidate location: which decision class(es) does it
belong to, is a log already there, is that log's evidence sufficient, and
what is the recommended fix — not just "covered or not."

Usage:
    python3 ast_decision_scanner.py --file path/to/service.py
    python3 ast_decision_scanner.py --pr                 # diff vs main
    python3 ast_decision_scanner.py --staged             # staged files

Output: a JSON array of placement-plan entries on stdout (see PlacementEntry).
Exit codes: 0 = scanned successfully (regardless of findings) | 2 = usage/parse error
"""

import ast, os, sys, re, json, argparse, subprocess, fnmatch
import importlib.util
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Iterator, Optional, Tuple

MANIFEST_RELATIVE_PATH = os.environ.get("RAVEN_MANIFEST_PATH", ".raven/manifest.json")

# A per-class detector either finds nothing, or returns the AST node the finding
# anchors to, a human-readable reason, and a fixed confidence score.
Hit = Optional[Tuple[ast.AST, str, float]]


# ── Minimum evidence per decision class (from the Decision-Point Taxonomy) ─────

MIN_EVIDENCE_BY_CLASS = {
    "Routing":          ["selected_option", "available_options", "reason_code", "policy_version", "trace_id"],
    "Policy or Guard":  ["actor", "requested_action", "resource", "required_permission", "decision", "reason_code", "policy_version"],
    "Eligibility":       ["task_id", "risk_score", "threshold", "eligibility_result", "reason_code", "next_action", "rule_version"],
    "State Transition":  ["object_id", "previous_state", "requested_state", "final_state", "trigger", "result", "reason_code"],
    "Dependency":        ["dependency_name", "operation", "duration_ms", "result", "error_class", "attempt", "trace_id"],
    "Recovery":          ["triggering_error", "attempt", "max_attempts", "backoff_ms", "recovery_selected", "fallback_target", "exit_condition", "result"],
    "Outcome":           ["task_id", "final_status", "duration_ms", "stage", "result", "reason_code", "impact_scope"],
}

# D-324 (school-management-system false-positive investigation) — the base "Outcome"
# set above was designed around a pipeline/async-task mental model (task_id, stage,
# impact_scope all name concepts a tracked job moving through stages has, that a plain
# synchronous CRUD handler does not). Confirmed real-world mismatch: a FastAPI
# `create_student` endpoint's business-decision log (student_id, grade_level) was held
# to the same bar as a multi-stage batch pipeline. Used in place of the base set (a
# substitution via make_entry's required_fields_override, not an addition) for an
# Outcome finding on a function with no loop anywhere in its body — see
# _is_simple_sync_operation(). Kept deliberately non-trivial (not "log anything") —
# still requires the operation's terminal status and a reason for it.
SIMPLE_OUTCOME_EVIDENCE_FIELDS = ["final_status", "result", "reason_code", "duration_ms"]

# G31 (RAVEN-LOG-GAP-VALIDATION.md) — raven-eval's own gate ("Version fields present",
# "Retrieval flags present", raven-eval/SKILL.md's exit criteria) named these fields in
# prose only, with nothing deterministic checking for them. Applied as EXTRA required
# fields on top of the base "Dependency" set — not a new decision class — so the
# existing class→governance/risk/cost lookups (keyed on the 7 canonical class names)
# stay untouched. Deliberately not folded into schema_version: these are optional
# context-nested fields, same treatment as raven-retry's fields, not a breaking change.
EVAL_EXTRA_EVIDENCE_FIELDS = [
    "model_version", "prompt_version", "policy_version",
    "retrieval_document_ids", "retrieval_failed", "input_ref", "output_ref",
]

# G2 (RAVEN-LOG-GAP-VALIDATION.md) — the base "Recovery" evidence set applies
# identically to any try/fallback shape, so it can't distinguish a real retry
# from an unrelated fallback. Applied as EXTRA required fields (same mechanism
# as EVAL_EXTRA_EVIDENCE_FIELDS/G31 above), but only at the two call sites that
# are structurally retry-specific — a RETRY_DECORATOR_RE-decorated function
# (_detect_recovery_decorator) or a retry loop with a backoff/sleep except
# handler (_detect_recovery_retry_loop) — never at the generic
# _detect_recovery_try_fallback site, which has no retry-specific signal to
# key off of.
RETRY_EXTRA_EVIDENCE_FIELDS = ["retry_policy_version", "error_code"]

# G4 (RAVEN-LOG-GAP-VALIDATION.md) — the retry-instrumentation-contract.md's
# "Recommended exit conditions" enum. MIN_EVIDENCE_BY_CLASS["Recovery"] already
# requires an `exit_condition` KEY to be present (checked by
# _evidence_status_for_fields/_literal_dict_keys), but never validates its
# VALUE — a call like `raven_log(..., context={"exit_condition": "done"})`
# passes today even though "done" isn't a contract value. Checked only for the
# two retry-specific call sites (same scoping as RETRY_EXTRA_EVIDENCE_FIELDS)
# via make_entry's validate_exit_condition_enum flag.
EXIT_CONDITION_ENUM = {
    "SUCCESS", "MAX_ATTEMPTS_REACHED", "NON_RETRYABLE_ERROR",
    "DEADLINE_EXCEEDED", "CANCELLED", "CIRCUIT_OPEN", "FALLBACK_SELECTED",
}

# Narrow, precision-first allowlist — a false negative here just means an LLM-provider
# call gets treated as a plain Dependency finding (base evidence set only), never a
# false block. Deliberately excludes boto3 and bare `oci` (both used for far more than
# Bedrock / OCI Generative AI; would false-positive every S3 or Object Storage call as
# an LLM-provider dependency) — those two are matched by what the call targets instead,
# see _calls_cloud_llm(). Matched against the full dotted module path, so a submodule
# (openai.types, oci.generative_ai_inference.models) counts as its provider.
LLM_PROVIDER_NAME_RE = re.compile(
    r"^(openai|anthropic|langchain\w*|llama_index|llama_cpp|cohere|mistralai|"
    r"google\.generativeai|google\.genai|genai|vertexai|transformers|ollama|groq|together|"
    r"replicate|huggingface_hub|litellm|azure\.ai\.inference|oci\.generative_ai\w*)(\..+)?$",
    re.IGNORECASE,
)

# Cloud SDK calls that are LLM calls even though their import (boto3, oci) is not:
# an OCI module named generative_ai* (oci.generative_ai_inference.GenerativeAiInferenceClient)
# or a boto3/session client for a Bedrock runtime service.
_OCI_GENAI_ATTR_RE = re.compile(r"^generative_ai", re.IGNORECASE)
_BEDROCK_SERVICE_RE = re.compile(r"^bedrock(-agent)?-runtime$", re.IGNORECASE)

# G13/G14 — bumped manually when this file's classification logic changes meaningfully
# (new decision class, changed MIN_EVIDENCE_BY_CLASS, changed detection heuristics).
# Read by logging-plan-store.py so a persisted plan can tell "the ruleset that produced
# these findings changed" apart from "the code changed."
RULESET_VERSION = "1"

DEFAULT_EVENT_BY_CLASS = {
    "Routing":         ("route.selected", "INFO"),
    "Policy or Guard": ("authorization.denied", "WARN"),
    "Eligibility":      ("eligibility.evaluated", "INFO"),
    "State Transition": ("state.transition", "INFO"),
    "Dependency":       ("dependency.call_completed", "INFO"),
    "Recovery":         ("recovery.selected", "WARN"),
    "Outcome":          ("operation.completed", "INFO"),
}

# Auto Log & Guardrail Plugin policy-mapping translation (task T04). Two classes
# — State Transition and Outcome — don't fit any of the plugin's 4 risk
# categories (injection / token_exhaustion / tool_abuse / data_exposure); they're
# business-logic-integrity risks, not security risks in that sense. Left absent
# from this map on purpose rather than force-fit — see
# auto-log-guardrail-plugin-cross-cutting-decisions.md (T04) for the reasoning.
RISK_CATEGORY_BY_CLASS = {
    "Routing":         "tool_abuse",
    "Policy or Guard": "data_exposure",
    "Eligibility":     "tool_abuse",
    "Dependency":      "token_exhaustion",
    "Recovery":        "token_exhaustion",
}

# Governance/stakes-routing inputs (task T10) — how costly and how reversible a
# wrong classification is for each decision class, independent of how confident
# the *detector* is that it found the right shape. Rough defaults, not
# back-tested: per the plugin's own confidence-calibration principle (see
# raven-rca), the real thresholds should come from verified incidents, not an
# assumed constant — treat these as a starting point to calibrate, not a
# finished answer.
REVERSIBILITY_BY_CLASS = {
    "Routing":           "reversible",
    "Policy or Guard":   "irreversible",
    "Eligibility":       "reversible",
    "State Transition":  "conditionally_reversible",
    "Dependency":        "irreversible",
    "Recovery":          "irreversible",
    "Outcome":           "irreversible",
}
COST_BY_CLASS = {
    "Routing":           "low",
    "Policy or Guard":   "high",
    "Eligibility":       "medium",
    "State Transition":  "medium",
    "Dependency":        "medium",
    "Recovery":          "high",
    "Outcome":           "low",
}
# Below this, a finding is "low confidence" for governance routing purposes —
# reuses the same 0.85 cut mandatory_status already uses, so there is one
# confidence scale in this script, not two competing ones.
GOVERNANCE_CONFIDENCE_THRESHOLD = 0.85


@dataclass
class PlacementEntry:
    file: str
    line: int
    symbol: str
    decision_classes: list
    mandatory_status: str          # "mandatory" | "recommended" | "diagnostic-only" | "no-log"
    recommended_event_name: str
    recommended_severity: str
    required_fields: list
    existing_log_status: str       # "none" | "insufficient" | "sufficient" | "unverifiable"
    missing_evidence: list
    classification_confidence: float
    reason: str
    related_rca_use_case: str = ""
    risk_category: list = field(default_factory=list)          # T04/T07 — may be empty, see RISK_CATEGORY_BY_CLASS
    reversibility: str = ""                                     # T10 — "reversible" | "conditionally_reversible" | "irreversible"
    cost: str = ""                                              # T10 — "low" | "medium" | "high"
    governance_routing: str = ""                                # T10 — "auto_pass" | "standard_review" | "blocking_gate"
    owner: str = ""                                             # T11 — from CODEOWNERS or manifest.json, "" if unresolved
    cost_benefit: str = ""                                       # T12 — cost of adding vs. cost of leaving open, one line
    rule_id: str = ""                                            # M2 — the raven-rules.py rule this entry comes from, "" for class detectors


# ── Shared rule engine (gap plan M2) ───────────────────────────────────────────
# raven-rules.py is the one rule set this scanner and log-coverage-check.py
# both apply, so they report the same rule ids for the same code. It sits
# next to this file (skills/raven-decision-map/scripts/, every plugin copy,
# CI's vendored .github/raven/) or in the project's Raven scripts folder.
# Missing -> rules off (fail-open); the class detectors below still run.

_rules_cache = {"loaded": False, "mod": None}


def _load_rules():
    if not _rules_cache["loaded"]:
        _rules_cache["loaded"] = True
        here = Path(__file__).resolve().parent
        for candidate in (here / "raven-rules.py", Path.cwd() / ".claude" / "scripts" / "raven-rules.py",
                          Path.cwd() / "raven-core" / "raven-rules.py"):
            if candidate.exists():
                try:
                    spec = importlib.util.spec_from_file_location("raven_rules", candidate)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    _rules_cache["mod"] = mod
                    break
                except Exception:
                    continue
    return _rules_cache["mod"]


# ── Shared structural helpers (kept consistent with log-coverage-check.py) ─────

LOG_FUNC_NAMES   = {"raven_log"}
LOG_METHOD_NAMES = {"error", "warning", "critical", "exception", "info", "debug"}
LOG_OBJ_NAMES    = {"logger", "log"}

STDLIB_MODULES = {
    "os", "sys", "re", "io", "json", "time", "datetime", "math", "random",
    "itertools", "functools", "collections", "typing", "enum", "dataclasses",
    "abc", "asyncio", "logging", "pathlib", "subprocess", "threading",
    "multiprocessing", "queue", "socket", "ssl", "http", "urllib", "email",
    "string", "copy", "contextlib", "warnings", "traceback", "inspect",
    "importlib", "unittest", "argparse", "configparser", "csv", "sqlite3",
    "hashlib", "hmac", "base64", "uuid", "decimal", "fractions", "statistics",
    "heapq", "bisect", "array", "struct", "pickle", "shelve", "zlib", "gzip",
    "tarfile", "zipfile", "tempfile", "shutil", "glob", "fnmatch", "platform",
    "getpass", "pwd", "grp", "signal", "errno", "ctypes", "ast", "dis",
    "token", "tokenize", "keyword", "types", "weakref", "gc", "site",
    "sysconfig", "venv", "test", "__future__",
}

# Stdlib modules that still perform genuine external network I/O — being part of
# the standard library does not mean "not external." Without this carve-out,
# _collect_io_names() below treats these as non-external solely because they're
# in STDLIB_MODULES, making any code that uses e.g. urllib.request instead of
# requests/httpx completely invisible to Dependency-class detection (confirmed
# bug: a real urllib.request-based HTTP client produced zero scanner findings —
# not even a "no-log" exemption on the function making the call). Deliberately
# excludes `subprocess` — also a real external-dependency surface, but used
# pervasively throughout this repo's own hook scripts; adding it here would need
# its own baseline decision, not a quick fix alongside this one.
NETWORK_IO_STDLIB_MODULES = {
    "urllib", "http", "socket", "smtplib", "ftplib", "telnetlib",
    "imaplib", "poplib", "nntplib",
}

AUTH_CALL_RE = re.compile(
    r"(authoriz|permission|is_allowed|can_access|require_role|enforce_policy|"
    r"check_role|is_admin|rate_limit|feature_flag|tool_use)",
    re.IGNORECASE,
)
ELIGIBILITY_NAME_RE = re.compile(r"(score|threshold|risk|eligib)", re.IGNORECASE)
RETRY_DECORATOR_RE  = re.compile(r"(retry|retriable|backoff|circuit_?breaker)", re.IGNORECASE)
BACKOFF_CALL_RE      = re.compile(r"(sleep|backoff)", re.IGNORECASE)

# G3 (RAVEN-LOG-GAP-VALIDATION.md) — exception type names shaped like an
# authentication/authorization failure per retry-instrumentation-contract.md's
# Error Classification table ("Normally do not retry" / "Do not retry"). Used
# to flag a retry path that swallows one of these without an explicit
# no-retry marker — blind-retrying an auth failure masks a real
# permissions/config problem as transient.
AUTH_ERROR_EXC_RE = re.compile(
    r"(auth(entication)?error|permissiondenied|forbidden|unauthorized|"
    r"authorizationerror|invalidcredentials|accessdenied)",
    re.IGNORECASE,
)
STATE_ATTR_NAMES     = {"status", "state"}
CRITICAL_NAME_RE = re.compile(
    r"^(create|update|delete|process|pay|charge|transfer|submit|"
    r"approve|reject|cancel|refund|register|authenticate|authorize|"
    r"execute|dispatch|apply|commit|publish|notify|trigger|send)",
    re.IGNORECASE,
)


def _is_log_call(node: ast.AST) -> bool:
    """True for a raven_log(...) call or a logger.error/warning/info/... style call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id in LOG_FUNC_NAMES:
        return True
    if (isinstance(func, ast.Attribute) and func.attr in LOG_METHOD_NAMES
            and isinstance(func.value, ast.Name) and func.value.id in LOG_OBJ_NAMES):
        return True
    return False


def _is_raven_log_call(node: ast.AST) -> bool:
    """True only for raven_log(...) — narrower than _is_log_call, used when checking evidence."""
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "raven_log"


def _walk_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Yield node and descendants without crossing into nested function/class/lambda bodies."""
    yield node
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk_scope(child)


def _find_raven_log_calls_in_body(stmts: list) -> list:
    """Every raven_log(...) call reachable from stmts, not crossing into nested functions."""
    calls = []
    for stmt in stmts:
        for node in _walk_scope(stmt):
            if _is_raven_log_call(node):
                calls.append(node)
    return calls


def _body_has_any_log(stmts: list) -> bool:
    """True if any raven_log()/logger.x() call is reachable from stmts."""
    for stmt in stmts:
        for node in _walk_scope(stmt):
            if _is_log_call(node):
                return True
    return False


def _literal_dict_keys(dict_node: ast.AST) -> Optional[list]:
    """Best-effort: keys of a literal dict AST node, or None if not a literal dict."""
    if not isinstance(dict_node, ast.Dict):
        return None
    keys = []
    for k in dict_node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
        else:
            return None  # non-literal key — can't verify statically
    return keys


def _literal_dict_string_value(dict_node: ast.AST, key: str) -> Optional[str]:
    """Best-effort: the literal string value bound to `key` in a literal dict AST
    node, or None if the dict isn't literal, `key` isn't present, or its value
    isn't a literal string (in which case it's unverifiable, not invalid — same
    conservative bias as _literal_dict_keys)."""
    if not isinstance(dict_node, ast.Dict):
        return None
    for k, v in zip(dict_node.keys, dict_node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else None
    return None


def _retry_exit_condition_has_invalid_literal(enclosing_stmts: list) -> bool:
    """G4: True if some raven_log() call in scope sets a literal string
    `exit_condition` that isn't one of the contract's enum values. A missing,
    non-literal, or absent-context exit_condition is NOT flagged here — that's
    _evidence_status_for_fields's presence check's job; this only catches a
    value that's confidently wrong, never guesses at an unverifiable one."""
    for call in _find_raven_log_calls_in_body(enclosing_stmts):
        for kw in call.keywords:
            if kw.arg != "context":
                continue
            value = _literal_dict_string_value(kw.value, "exit_condition")
            if value is not None and value not in EXIT_CONDITION_ENUM:
                return True
    return False


def _evidence_status_for_fields(enclosing_stmts: list, required: list) -> Tuple[str, list]:
    """
    Inspect raven_log() calls in scope for the given required field names (only
    checked inside the call's `context={...}` literal, since that's the only place
    structured evidence can live). Returns (status, missing_fields). Split out from
    _evidence_status() (G31) so callers can check an arbitrary extra field list —
    e.g. raven-eval's LLM-provider evidence — without that list needing to be a
    registered decision class in MIN_EVIDENCE_BY_CLASS.
    """
    calls = _find_raven_log_calls_in_body(enclosing_stmts)
    if not calls:
        return "none", list(required)

    best_missing = list(required)
    saw_unverifiable = False
    for call in calls:
        context_arg = None
        for kw in call.keywords:
            if kw.arg == "context":
                context_arg = kw.value
                break
        if context_arg is None:
            missing = list(required)
        else:
            keys = _literal_dict_keys(context_arg)
            if keys is None:
                saw_unverifiable = True
                continue
            missing = [f for f in required if f not in keys]
        if len(missing) < len(best_missing):
            best_missing = missing

    if not best_missing:
        return "sufficient", []
    if saw_unverifiable and best_missing == list(required):
        return "unverifiable", list(required)
    return "insufficient", best_missing


def _evidence_status(enclosing_stmts: list, decision_class: str,
                      required_override: Optional[list] = None) -> Tuple[str, list]:
    """Thin wrapper over _evidence_status_for_fields() for a registered decision class —
    kept as the public entry point every existing caller already uses. required_override
    (D-324), when given, replaces the class's MIN_EVIDENCE_BY_CLASS list entirely for this
    one check — a substitution, not an addition (contrast extra_required_fields, which is
    additive) — used for a decision class whose base field set doesn't fit this specific
    finding's structural shape without inventing a new decision class name."""
    required = required_override if required_override is not None else MIN_EVIDENCE_BY_CLASS.get(decision_class, [])
    return _evidence_status_for_fields(enclosing_stmts, required)


PROJECT_ROOT_MARKERS = (".git", "pyproject.toml", "setup.py", "requirements.txt", ".raven")


def _find_project_root(start: Path) -> Path:
    """Walk up from start looking for a repo root marker — same walk-up
    convention as resolve_owner()'s CODEOWNERS/manifest lookup below. Falls
    back to start itself if no marker is found within a bounded number of
    hops, matching this module's fail-open posture (an unresolved root just
    means the local-first-party exclusion below finds nothing, not an
    error)."""
    current = start.resolve()
    for _ in range(8):
        if any((current / marker).exists() for marker in PROJECT_ROOT_MARKERS):
            return current
        if current.parent == current:
            break
        current = current.parent
    return start.resolve()


def _is_local_first_party_module(root_name: str, project_root: Path) -> bool:
    """True if root_name resolves to a real file/package inside project_root —
    i.e., it's the project's OWN code imported absolutely (the common FastAPI/
    Django convention `from app import config` instead of `from . import
    config`), not a genuine third-party dependency living in site-packages."""
    return (
        (project_root / f"{root_name}.py").exists()
        or (project_root / root_name / "__init__.py").exists()
        or (project_root / root_name).is_dir()
    )


def _collect_io_names(tree: ast.AST, path: str = "", project_root: Optional[Path] = None) -> set:
    """Names bound to any non-stdlib, non-relative, non-local-first-party import,
    OR a stdlib module that still performs genuine external network I/O (see
    NETWORK_IO_STDLIB_MODULES) — the Dependency signal.

    Confirmed bug (school-management-system demo project): an absolute import
    of the project's OWN sibling module (`from app import config`) looked
    identical to importing a real third-party/network dependency, since the
    only prior exclusion was "is it stdlib." That made correct instrumentation
    self-defeating — the raven_log() call's own `service=config.SERVICE`
    argument was what made a function look like it called an external
    dependency. `_is_local_first_party_module` closes that gap the same way
    `_is_test_file` closes the analogous test-fixture false positive.

    project_root is an explicit override for callers that scan a RECONSTRUCTED
    copy of a file living outside the real project tree (instrument-on-write.py
    writes the post-edit content to an isolated tempfile.mkdtemp() location to
    avoid touching disk before the edit is approved) — walking up from that
    tmp path would never find the real project's markers. Callers scanning a
    file in its real location can omit this and let the path-based walk-up
    below resolve it."""
    names = set()
    if project_root is None:
        project_root = _find_project_root(Path(path).parent) if path else None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root and (root not in STDLIB_MODULES or root in NETWORK_IO_STDLIB_MODULES):
                    if project_root and _is_local_first_party_module(root, project_root):
                        continue
                    names.add(alias.asname or root)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            mod = (node.module or "").split(".")[0]
            if mod and (mod not in STDLIB_MODULES or mod in NETWORK_IO_STDLIB_MODULES):
                if project_root and _is_local_first_party_module(mod, project_root):
                    continue
                for alias in node.names:
                    names.add(alias.asname or alias.name)
    return names


def _collect_llm_provider_names(tree: ast.AST) -> set:
    """Names bound to an import matching LLM_PROVIDER_NAME_RE (G31) — the subset of
    io_names, if any, that a Dependency finding needs raven-eval's extra evidence
    fields for. Same import-walking shape as _collect_io_names(), filtered narrower."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root and LLM_PROVIDER_NAME_RE.match(alias.name):
                    names.add(alias.asname or root)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            mod = node.module or ""
            for alias in node.names:
                # `from google import genai` / `from oci import generative_ai_inference`
                # name the provider in the imported symbol, not the module.
                if mod and (LLM_PROVIDER_NAME_RE.match(mod)
                            or LLM_PROVIDER_NAME_RE.match(f"{mod}.{alias.name}")):
                    names.add(alias.asname or alias.name)
    return names


def _calls_cloud_llm(node: ast.AST) -> bool:
    """True if node reaches an LLM through a general-purpose cloud SDK: an OCI
    generative_ai* module attribute, or a client created for a Bedrock runtime
    (boto3.client("bedrock-runtime"), session.client(service_name="bedrock-agent-runtime"))."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and _OCI_GENAI_ATTR_RE.match(sub.attr):
            return True
        if isinstance(sub, ast.Call):
            func = sub.func
            fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if fname != "client":
                continue
            service = sub.args[0] if sub.args else next(
                (k.value for k in sub.keywords if k.arg == "service_name"), None)
            if (isinstance(service, ast.Constant) and isinstance(service.value, str)
                    and _BEDROCK_SERVICE_RE.match(service.value)):
                return True
    return False


def _calls_external(node: ast.AST, io_names: set) -> bool:
    """True if node contains a call to an attribute of one of io_names anywhere below it."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id in io_names:
            return True
    return False


def _decorator_names(func_node: ast.AST) -> list:
    """Decorator names (as strings) for a FunctionDef/AsyncFunctionDef, call or bare."""
    names = []
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Attribute):
            names.append(dec.attr)
        elif isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Attribute):
                names.append(dec.func.attr)
            elif isinstance(dec.func, ast.Name):
                names.append(dec.func.id)
    return names


def _build_enclosing_function_map(tree: ast.AST) -> dict:
    """Map id(node) -> nearest enclosing FunctionDef/AsyncFunctionDef (or None at module level)."""
    mapping = {}

    def walk(node: ast.AST, current: Optional[ast.AST]) -> None:
        """Record node's enclosing function, then recurse with the updated current one."""
        mapping[id(node)] = current
        nxt = current
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nxt = node
        for child in ast.iter_child_nodes(node):
            walk(child, nxt)

    walk(tree, None)
    return mapping


def _node_name(node: ast.AST) -> str:
    """Best-effort human-readable label for a Name/Constant/Call/Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Call):
        f = node.func
        return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "<call>")
    if isinstance(node, ast.Attribute):
        return node.attr
    return "<expr>"


# ── Per-class detectors — each returns a list of (ast_node, reason, confidence) ─

def _detect_policy_or_guard(if_node: ast.If) -> Hit:
    """An `if` whose test calls something matching AUTH_CALL_RE — a policy/guard check."""
    for node in ast.walk(if_node.test):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name and AUTH_CALL_RE.search(name):
                return (if_node, f"branch guards on '{name}' — an authorization/policy/guard check", 0.95)
    return None


def _detect_eligibility(if_node: ast.If) -> Hit:
    """An if/else comparing a score/threshold/risk/eligibility-named value, with both branches present."""
    if not if_node.orelse:
        return None
    test = if_node.test
    if not isinstance(test, ast.Compare):
        return None
    names = [n for n in ast.walk(test) if isinstance(n, (ast.Name, ast.Attribute))]
    for n in names:
        label = n.id if isinstance(n, ast.Name) else n.attr
        if ELIGIBILITY_NAME_RE.search(label):
            return (if_node, f"branch compares '{label}' against a threshold with distinct outcomes", 0.85)
    return None


def _detect_routing(if_node: ast.If) -> Hit:
    """An if/else where both branches assign a different value to the same target name."""
    if not if_node.orelse:
        return None
    if_assigns = {t.id: _node_name(s.value) for s in if_node.body if isinstance(s, ast.Assign)
                  for t in s.targets if isinstance(t, ast.Name)}
    else_assigns = {t.id: _node_name(s.value) for s in if_node.orelse if isinstance(s, ast.Assign)
                    for t in s.targets if isinstance(t, ast.Name)}
    for target, if_val in if_assigns.items():
        if target in else_assigns and else_assigns[target] != if_val:
            return (if_node, f"branches assign different values to '{target}' — a routing/selection decision", 0.85)
    return None


def _detect_state_transition(assign_node: ast.Assign) -> Hit:
    """An assignment to a `.status`/`.state`-style attribute — a durable state transition."""
    for target in assign_node.targets:
        if isinstance(target, ast.Attribute) and target.attr in STATE_ATTR_NAMES:
            return (assign_node, f"assignment to '{target.attr}' — a durable state transition", 0.9)
    return None


def _detect_dependency_function(func_node: ast.AST, io_names: set) -> Hit:
    """A function whose body calls an attribute of a non-stdlib-imported name."""
    if io_names and _calls_external(func_node, io_names):
        return (func_node, f"function '{func_node.name}' calls an externally-imported dependency", 0.85)
    return None


def _detect_recovery_decorator(func_node: ast.AST) -> Hit:
    """A function decorated with something matching RETRY_DECORATOR_RE."""
    for name in _decorator_names(func_node):
        if RETRY_DECORATOR_RE.search(name):
            return (func_node, f"function '{func_node.name}' has a retry/backoff/circuit-breaker decorator", 0.95)
    return None


def _try_body_calls_external(try_node: ast.Try, io_names: set) -> bool:
    """True if the try body (not the handlers) calls an external dependency."""
    for stmt in try_node.body:
        if _calls_external(stmt, io_names):
            return True
    return False


def _handler_has_recovery_action(handler: ast.ExceptHandler) -> bool:
    """Any call in the handler body — retry, fallback, cache, degrade, or a bare
    reassignment all count; a handler that only re-raises or passes does not."""
    for stmt in handler.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                return True
    return False


def _detect_recovery_try_fallback(try_node: ast.Try, io_names: set) -> Hit:
    """A try/except that reassigns its try-body target in the handler, or recovers
    from a failed dependency call some other way (see _handler_has_recovery_action)."""
    # Higher-confidence shape: the same variable reassigned in try and except
    # (e.g. `response = primary(...)` / `except: response = fallback(...)`).
    try_targets = {t.id for s in try_node.body if isinstance(s, ast.Assign)
                   for t in s.targets if isinstance(t, ast.Name)}
    if try_targets:
        for handler in try_node.handlers:
            for s in handler.body:
                if isinstance(s, ast.Assign):
                    for t in s.targets:
                        if isinstance(t, ast.Name) and t.id in try_targets:
                            return (try_node, "try/except reassigns the same target in its handler — a fallback pattern", 0.9)

    # Broader shape: a dependency call fails and the handler takes SOME
    # recovery action (retry, fallback, cache, degrade) even without
    # reassigning a variable — e.g. `except TimeoutError: retry_search()`.
    if _try_body_calls_external(try_node, io_names):
        for handler in try_node.handlers:
            if _handler_has_recovery_action(handler):
                return (try_node, "except handler takes a recovery action after a dependency call failed", 0.8)

    return None


def _detect_recovery_retry_loop(for_node: ast.AST) -> Hit:
    """A for/async-for loop containing a try/except whose handler calls sleep/backoff."""
    has_backoff_except = False
    for sub in ast.walk(for_node):
        if isinstance(sub, ast.ExceptHandler):
            if any(isinstance(c, ast.Call) and BACKOFF_CALL_RE.search(_node_name(c))
                   for c in ast.walk(sub) if isinstance(c, ast.Call)):
                has_backoff_except = True
    if has_backoff_except:
        return (for_node, "retry loop with a backoff/sleep call in its except handler", 0.85)
    return None


def _except_handler_type_names(handler: ast.ExceptHandler) -> list:
    """Exception type name(s) an except handler catches, by simple name — mirrors
    log-coverage-check.py's _except_is_timeout, generalized to any name list."""
    t = handler.type
    names = []
    if isinstance(t, ast.Name):
        names.append(t.id)
    elif isinstance(t, ast.Attribute):
        names.append(t.attr)
    elif isinstance(t, ast.Tuple):
        for elt in t.elts:
            if isinstance(elt, ast.Name):
                names.append(elt.id)
            elif isinstance(elt, ast.Attribute):
                names.append(elt.attr)
    return names


def _handler_has_no_retry_marker(handler: ast.ExceptHandler) -> bool:
    """True if a raven_log() call in this handler's body carries an explicit
    no-retry marker — a literal `retryable=False` kwarg, or `"retryable": False`
    inside a literal `context={...}` dict. A non-literal/unverifiable value is
    NOT treated as a marker (same conservative bias as the rest of this file —
    an unverifiable claim doesn't excuse the blind-retry risk)."""
    for stmt in handler.body:
        for node in _walk_scope(stmt):
            if not _is_raven_log_call(node):
                continue
            for kw in node.keywords:
                if kw.arg == "retryable" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    return True
                if kw.arg == "context" and isinstance(kw.value, ast.Dict):
                    for k, v in zip(kw.value.keys, kw.value.values):
                        if (isinstance(k, ast.Constant) and k.value == "retryable"
                                and isinstance(v, ast.Constant) and v.value is False):
                            return True
    return False


def _detect_auth_error_retried_without_marker(node: ast.AST) -> Hit:
    """G3: an except handler (anywhere inside a retry-decorated function or a
    retry loop) that catches an AUTH_ERROR_EXC_RE-shaped exception without an
    explicit no-retry marker nearby. Per retry-instrumentation-contract.md's
    Error Classification table, auth/authorization failures should "normally
    not"/"do not" retry — silently retrying one masks a real permissions/config
    problem as a transient failure."""
    for handler in ast.walk(node):
        if not isinstance(handler, ast.ExceptHandler):
            continue
        if not any(AUTH_ERROR_EXC_RE.search(n) for n in _except_handler_type_names(handler)):
            continue
        if _handler_has_no_retry_marker(handler):
            continue
        return (handler, "except handler retries an auth-error-shaped exception "
                          "with no explicit no-retry marker", 0.9)
    return None


def _detect_loop_logging(for_or_while_node: ast.AST) -> Hit:
    """A log call sitting directly inside a loop body — a flood risk, not a decision point."""
    for stmt in for_or_while_node.body:
        for inner in _walk_scope(stmt):
            if _is_log_call(inner):
                return (inner, "log call sits directly inside a loop body — possible flooding, not a decision point", 0.9)
    return None


def _find_terminal_outcome(func_node: ast.AST) -> Hit:
    """The function's last statement, if it's a return/raise — its terminal outcome."""
    if not func_node.body:
        return None
    last = func_node.body[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return (last, f"terminal statement of function '{func_node.name}'", 0.7)
    return None


def _loop_can_partially_fail(loop_node: ast.AST) -> bool:
    """True if loop_node's own body contains an If or Try anywhere below it — the
    structural signal that some iterations of this loop could succeed while others
    fail or branch differently. A bare straight-line loop (e.g. `for k, v in
    changed_fields.items(): setattr(obj, k, v)`, ordinary multi-attribute-copy
    syntax) has no such signal and isn't "batch processing with partial failure"
    in any meaningful sense, even though it's structurally a loop."""
    for inner in ast.walk(loop_node):
        if inner is loop_node:
            continue
        if isinstance(inner, (ast.If, ast.Try)):
            return True
    return False


def _is_simple_sync_operation(func_node: ast.AST) -> bool:
    """D-324: True when func_node has no loop capable of partially failing
    (see _loop_can_partially_fail) anywhere in its body — a single-step operation,
    not a multi-item batch or multi-stage pipeline. Distinguishes the two
    structural shapes MIN_EVIDENCE_BY_CLASS's base "Outcome" fields were written
    for (a tracked job moving through stages, with per-item partial failure —
    task_id/stage/impact_scope) from a plain synchronous create/update/delete
    handler, which has neither. Confirmed real-world mismatch: a FastAPI
    `create_student` endpoint's business-decision log was held to the same
    evidence bar as an async multi-stage pipeline; `update_student`'s trivial
    `for field, value in changed_fields.items(): setattr(...)` loop was the
    concrete case that motivated requiring branch/failure capability, not just
    loop presence. A nested function containing a qualifying loop still counts as
    "not simple" — conservative by design, same posture as the rest of this
    file's detectors."""
    for node in ast.walk(func_node):
        if node is func_node:
            continue
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)) and _loop_can_partially_fail(node):
            return False
    return True


def _is_pure_calculation(func_node: ast.AST, io_names: set) -> bool:
    """No branch-selection, no external call, no state mutation, no raise."""
    for node in ast.walk(func_node):
        if isinstance(node, ast.Raise):
            return False
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr in STATE_ATTR_NAMES:
                    return False
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in io_names:
            return False
        if isinstance(node, ast.If):
            return False
    return True


def _governance_inputs_for(classes: list) -> Tuple[list, str, str]:
    """
    Risk category, reversibility, and cost for a finding's decision class(es)
    (task T04/T10). When a finding spans multiple classes, reversibility/cost
    take the more conservative (worse-case) value across them, matching how
    `existing_log_status` already takes the worst case across classes.
    """
    risk_categories = sorted({RISK_CATEGORY_BY_CLASS[c] for c in classes if RISK_CATEGORY_BY_CLASS.get(c)})

    reversibility_order = {"reversible": 0, "conditionally_reversible": 1, "irreversible": 2}
    reversibilities = [REVERSIBILITY_BY_CLASS.get(c, "reversible") for c in classes]
    reversibility = max(reversibilities, key=lambda r: reversibility_order[r]) if reversibilities else "reversible"

    cost_order = {"low": 0, "medium": 1, "high": 2}
    costs = [COST_BY_CLASS.get(c, "low") for c in classes]
    cost = max(costs, key=lambda c: cost_order[c]) if costs else "low"

    return risk_categories, reversibility, cost


def _route_for_governance(confidence: float, reversibility: str, cost: str) -> str:
    """
    Section H's 2-D routing rule: confidence alone isn't enough to decide
    whether a finding needs a blocking gate — a wrong low-stakes routing call
    and a wrong high-stakes authorization call shouldn't be governed the same
    way just because a detector is equally sure about both.

    - blocking_gate: low confidence AND (irreversible OR high-cost)
    - auto_pass:     high confidence AND reversible AND low-cost
    - standard_review: everything else
    """
    high_confidence = confidence >= GOVERNANCE_CONFIDENCE_THRESHOLD
    high_stakes = reversibility == "irreversible" or cost == "high"

    if not high_confidence and high_stakes:
        return "blocking_gate"
    if high_confidence and reversibility == "reversible" and cost == "low":
        return "auto_pass"
    return "standard_review"


# ── Owner resolution (task T11) ─────────────────────────────────────────────────

def _parse_codeowners(codeowners_path: Path) -> list:
    """Return [(pattern, owner), ...] in file order — CODEOWNERS matching is
    last-match-wins, the same semantics as .gitignore."""
    rules = []
    if not codeowners_path.exists():
        return rules
    for line in codeowners_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern, owners = parts[0], parts[1:]
        rules.append((pattern, " ".join(owners)))
    return rules


def _match_codeowners(file_path: str, rules: list) -> str:
    """Last matching rule wins, per CODEOWNERS semantics. fnmatch-based —
    good enough for simple prefix/extension patterns; does not implement
    full gitignore-style recursive-glob semantics."""
    owner = ""
    for pattern, rule_owner in rules:
        p = pattern.lstrip("/")
        if (fnmatch.fnmatch(file_path, p) or fnmatch.fnmatch(file_path, p + "*")
                or fnmatch.fnmatch(os.path.basename(file_path), p)):
            owner = rule_owner
    return owner


def resolve_owner(file_path: str, project_root: Optional[Path] = None) -> str:
    """
    Resolve an owner for file_path (task T11), checked in this order:
    1. CODEOWNERS (standard GitHub convention, last-match-wins) — checked at
       .github/CODEOWNERS, CODEOWNERS, and docs/CODEOWNERS.
    2. .raven/manifest.json's "ownership" map (path-glob -> owner), a
       Raven-specific extension for repos without CODEOWNERS.
    3. .raven/manifest.json's top-level "owner" (org-wide default).
    4. "" if none of the above resolve anything — reported honestly, never
       guessed, matching raven-decision-map's own no-forced-answer principle.
    """
    root = project_root or Path(".")
    for candidate in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        codeowners_path = root / candidate
        if codeowners_path.exists():
            owner = _match_codeowners(file_path, _parse_codeowners(codeowners_path))
            if owner:
                return owner

    try:
        manifest = json.loads((root / MANIFEST_RELATIVE_PATH).read_text())
    except Exception:
        return ""

    for pattern, owner in manifest.get("ownership", {}).items():
        if fnmatch.fnmatch(file_path, pattern):
            return owner

    return manifest.get("owner", "")


# ── Cost/benefit framing (task T12) ─────────────────────────────────────────────

_COST_BENEFIT_TEMPLATES = {
    "blocking_gate": "Cost of adding: one structured event with {n} required field(s). "
                      "Cost of leaving open: {classes} finding with {cost} cost and "
                      "{reversibility} impact would have no evidence trail if it fails — "
                      "reconstructing what happened after the fact may not be possible.",
    "auto_pass": "Cost of adding: one structured event with {n} required field(s), "
                 "low-stakes and reversible if the field mapping needs a follow-up fix. "
                 "Cost of leaving open: minor — this path is low-cost and reversible even "
                 "if something is missed.",
    "standard_review": "Cost of adding: one structured event with {n} required field(s). "
                        "Cost of leaving open: a {classes} finding with {cost} cost and "
                        "{reversibility} impact — worth a human judgment call, not "
                        "significant enough on confidence alone to force a block.",
}


def _cost_benefit_framing(classes: list, required_fields: list, cost: str,
                           reversibility: str, governance_routing: str) -> str:
    """One line framing what adding the recommended event costs vs. what leaving
    the gap open costs (Section C's "risk/benefit framing per gap"). Falls back
    to a generic line for flood-risk/no-log entries, which have no decision
    class and no meaningful cost/benefit tradeoff to frame."""
    if not classes:
        return ""
    template = _COST_BENEFIT_TEMPLATES.get(governance_routing, _COST_BENEFIT_TEMPLATES["standard_review"])
    return template.format(
        n=len(required_fields), classes=" / ".join(classes),
        cost=cost or "unrated", reversibility=reversibility or "unrated",
    )


# ── Analysis ────────────────────────────────────────────────────────────────────

def _is_test_file(path: str) -> bool:
    """pytest's own discovery convention (test_*.py / *_test.py, or anywhere
    under a tests/ directory) — a test calling the code under test looks,
    structurally, identical to production code calling a real dependency;
    the AST pass has no way to know a call is exercised against a
    fixture/mock rather than a live system. Flagging every test as if it
    needed the same runtime observability as the production path it
    exercises produced 100% false-positive Dependency findings on ordinary
    monkeypatch-based unit tests (raven-enterprise#203) — every finding
    anchored to a test function or fixture, none to production code."""
    normalized = path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return "tests" in normalized.split("/") or "test" in normalized.split("/")


def analyze_file(path: str, project_root: Optional[Path] = None) -> list:
    """Scan one file and return its placement-plan entries (see PlacementEntry).

    project_root: see _collect_io_names' docstring — pass this when path is a
    reconstructed/tempfile copy of a file that really lives elsewhere."""
    entries = []
    if _is_test_file(path):
        return entries
    try:
        source = Path(path).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        print(f"  ⚠️  Syntax error in {path}: {e} — skipped (fail-open)", file=sys.stderr)
        return entries
    except Exception as e:
        print(f"  ⚠️  Could not parse {path}: {e} — skipped (fail-open)", file=sys.stderr)
        return entries

    io_names = _collect_io_names(tree, path, project_root)
    llm_provider_names = _collect_llm_provider_names(tree)
    enclosing = _build_enclosing_function_map(tree)
    file_owner = resolve_owner(path)  # T11 — same owner for every entry in this file

    def enclosing_body_for(node: ast.AST) -> list:
        """The statement list whose scope `node` belongs to — its own body if it's a
        function, otherwise its nearest enclosing function's body (or module body)."""
        func = enclosing.get(id(node))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.body
        return func.body if func is not None else tree.body

    # Functions that own at least one decision-point finding — populated during
    # pass 1, read during pass 2. Kept separate from `entries` because
    # ast.walk() visits a FunctionDef before the statements in its own body
    # (breadth-first order), so checking "does this function already have a
    # finding" against `entries` while still walking would miss findings that
    # haven't been produced yet.
    decision_functions = set()

    def make_entry(node: ast.AST, symbol: str, classes: list, reason: str,
                    confidence: float, rca_use_case: str = "",
                    extra_required_fields: list = None,
                    validate_exit_condition_enum: bool = False,
                    required_fields_override: dict = None) -> None:
        """Compute evidence status for `classes` and append a PlacementEntry for `node`.
        `extra_required_fields` (G31) adds an additional evidence check on top of the
        classes' own union — used for raven-eval's LLM-provider fields — without those
        fields needing to be a registered decision class. `validate_exit_condition_enum`
        (G4) additionally checks that if `exit_condition` is present, its literal value
        is one of the contract's enum values — not just that the key exists.
        `required_fields_override` (D-324) maps a class name to a REPLACEMENT field list
        for this one finding — used when a class's base MIN_EVIDENCE_BY_CLASS set doesn't
        fit this finding's structural shape (e.g. Outcome's pipeline-oriented fields on a
        plain synchronous CRUD handler) — a substitution, not an addition, and scoped to
        this single call so it never affects other findings of the same class."""
        body = enclosing_body_for(node)
        statuses, missing_all = [], []
        for c in classes:
            status, missing = _evidence_status(body, c, (required_fields_override or {}).get(c))
            statuses.append(status)
            missing_all.extend(f for f in missing if f not in missing_all)
        if extra_required_fields:
            status, missing = _evidence_status_for_fields(body, extra_required_fields)
            statuses.append(status)
            missing_all.extend(f for f in missing if f not in missing_all)
        if validate_exit_condition_enum and _retry_exit_condition_has_invalid_literal(body):
            # A confidently-wrong value is worse than merely "present" — treat it the
            # same as a missing field rather than letting a bad literal read as sufficient.
            statuses.append("insufficient")
            if "exit_condition" not in missing_all:
                missing_all.append("exit_condition")

        # Worst-case status wins: none > insufficient > unverifiable > sufficient
        order = {"none": 0, "insufficient": 1, "unverifiable": 2, "sufficient": 3}
        overall_status = min(statuses, key=lambda s: order[s]) if statuses else "none"

        mandatory = "mandatory" if confidence >= 0.85 else "recommended"
        if overall_status == "sufficient":
            missing_all = []

        event_name, severity = DEFAULT_EVENT_BY_CLASS.get(classes[0], ("event.recorded", "INFO"))
        risk_categories, reversibility, cost = _governance_inputs_for(classes)
        governance_routing = _route_for_governance(confidence, reversibility, cost)
        required = sorted(
            {f for c in classes for f in (required_fields_override or {}).get(c, MIN_EVIDENCE_BY_CLASS.get(c, []))}
            | set(extra_required_fields or [])
        )
        cost_benefit = _cost_benefit_framing(classes, required, cost, reversibility, governance_routing)

        entries.append(PlacementEntry(
            file=path, line=getattr(node, "lineno", 0), symbol=symbol,
            decision_classes=classes, mandatory_status=mandatory,
            recommended_event_name=event_name, recommended_severity=severity,
            required_fields=required,
            existing_log_status=overall_status, missing_evidence=missing_all,
            classification_confidence=confidence, reason=reason,
            related_rca_use_case=rca_use_case,
            risk_category=risk_categories, reversibility=reversibility,
            cost=cost, governance_routing=governance_routing,
            owner=file_owner, cost_benefit=cost_benefit,
        ))

        owner = node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else enclosing.get(id(node))
        if owner is not None:
            decision_functions.add(id(owner))

    # ── Pass 1: every non-function-level decision shape ─────────────────────
    for node in ast.walk(tree):

        if isinstance(node, ast.If):
            hit = _detect_policy_or_guard(node)
            if hit:
                n, reason, conf = hit
                make_entry(n, "<if>", ["Policy or Guard"], reason, conf, "Sensitive tool/data access denied")
                continue  # a branch is classified once, most-specific match first
            hit = _detect_eligibility(node)
            if hit:
                n, reason, conf = hit
                make_entry(n, "<if>", ["Eligibility"], reason, conf, "Task routed to human review")
                continue
            hit = _detect_routing(node)
            if hit:
                n, reason, conf = hit
                make_entry(n, "<if>", ["Routing"], reason, conf, "LLM provider selection")

        elif isinstance(node, ast.Assign):
            hit = _detect_state_transition(node)
            if hit:
                n, reason, conf = hit
                make_entry(n, "<assign>", ["State Transition"], reason, conf, "Cancelled job returns to running")

        elif isinstance(node, ast.Try):
            hit = _detect_recovery_try_fallback(node, io_names)
            if hit:
                n, reason, conf = hit
                make_entry(n, "<try>", ["Dependency", "Recovery"], reason, conf, "Vector database timeout")

        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            # G12: while loops were previously silently never checked here, despite
            # _detect_loop_logging's own parameter name (for_or_while_node) implying
            # otherwise — log-coverage-check.py's separate loop detector already
            # covered ast.While; this brings the two into agreement.
            hit = _detect_loop_logging(node)
            if hit:
                n, reason, conf = hit
                entries.append(PlacementEntry(
                    file=path, line=n.lineno, symbol="<loop>",
                    decision_classes=[], mandatory_status="recommended",
                    recommended_event_name="", recommended_severity="",
                    required_fields=[], existing_log_status="n/a", missing_evidence=[],
                    classification_confidence=conf, reason=reason,
                    related_rca_use_case="High-volume batch loop (route to raven-flood)",
                    owner=file_owner,
                ))
            else:
                hit = _detect_recovery_retry_loop(node)
                if hit:
                    n, reason, conf = hit
                    # G2/G4: this loop shape is structurally a retry, not just any
                    # Dependency/Recovery fallback — require retry-specific evidence
                    # and validate exit_condition's literal value too.
                    make_entry(n, "<for>", ["Dependency", "Recovery"], reason, conf, "Retry followed by fallback",
                               extra_required_fields=RETRY_EXTRA_EVIDENCE_FIELDS,
                               validate_exit_condition_enum=True)
                    # G3: independent of the base retry finding above — flag a
                    # blindly-retried auth error as its own mandatory finding.
                    auth_hit = _detect_auth_error_retried_without_marker(node)
                    if auth_hit:
                        an, areason, aconf = auth_hit
                        make_entry(an, "<except>", ["Recovery"], areason, aconf,
                                   "Non-retryable authentication failure")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            hit = _detect_recovery_decorator(node)
            if hit:
                n, reason, conf = hit
                # G2/G4: a RETRY_DECORATOR_RE match is structurally a retry, not just
                # any Recovery shape — require retry-specific evidence and validate
                # exit_condition's literal value too.
                make_entry(n, node.name, ["Recovery"], reason, conf, "Retry policy changed",
                           extra_required_fields=RETRY_EXTRA_EVIDENCE_FIELDS,
                           validate_exit_condition_enum=True)
                # G3: independent of the base retry finding above — flag a
                # blindly-retried auth error as its own mandatory finding.
                auth_hit = _detect_auth_error_retried_without_marker(node)
                if auth_hit:
                    an, areason, aconf = auth_hit
                    make_entry(an, node.name, ["Recovery"], areason, aconf,
                               "Non-retryable authentication failure")
            hit = _detect_dependency_function(node, io_names)
            if hit:
                n, reason, conf = hit
                # G31: an LLM/agent-provider call needs raven-eval's evidence fields too,
                # on top of the base Dependency set — same finding, richer requirement.
                is_llm_call = ((bool(llm_provider_names) and _calls_external(node, llm_provider_names))
                               or _calls_cloud_llm(node))
                extra = EVAL_EXTRA_EVIDENCE_FIELDS if is_llm_call else None
                make_entry(n, node.name, ["Dependency"], reason, conf, "Vector database timeout",
                           extra_required_fields=extra)

    # ── Shared rules (M2): every open finding is its own entry ──────────────
    # A function where any rule fires — satisfied or not — is never "pure
    # calculation"; that exemption used to swallow `except: pass` around a
    # database call (gap plan issue 2).
    rules = _load_rules()
    rule_findings = rules.evaluate(tree, source, path) if rules is not None else []
    rule_functions = {f["function_line"] for f in rule_findings if f.get("function_line")}
    for f in (rules.open_findings(rule_findings) if rules is not None else []):
        rule_id = f["rule_id"]
        classes = rules.RULE_DECISION_CLASSES.get(rule_id, [])
        required = list(rules.RULE_REQUIRED_FIELDS.get(rule_id, []))
        event_name, severity = DEFAULT_EVENT_BY_CLASS.get(classes[0] if classes else "", ("event.recorded", "INFO"))
        if rule_id in ("R-SWALLOW", "R-DOWNGRADE"):
            event_name, severity = "operation.failed", "WARN"
        risk_categories, reversibility, cost = _governance_inputs_for(classes)
        confidence = 0.9 if f["tier"] == "mandatory" else 0.7
        routing = _route_for_governance(confidence, reversibility, cost)
        entries.append(PlacementEntry(
            file=path, line=f["line"], symbol=f["symbol"], decision_classes=classes,
            mandatory_status=f["tier"], recommended_event_name=event_name,
            recommended_severity=severity, required_fields=required, existing_log_status="none",
            missing_evidence=required, classification_confidence=confidence,
            reason=f"{rule_id}: {f['detail']}", related_rca_use_case="",
            risk_category=risk_categories, reversibility=reversibility, cost=cost,
            governance_routing=routing, owner=file_owner,
            cost_benefit=_cost_benefit_framing(classes, required, cost, reversibility, routing),
            rule_id=rule_id,
        ))

    # ── Pass 2: function-level checks that depend on pass 1's full results ──
    # (outcome detection and the pure-calculation exemption both need to know
    # whether anything *inside* the function already produced a finding).
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.lineno in rule_functions and id(node) not in decision_functions \
                and not CRITICAL_NAME_RE.match(node.name):
            continue  # a rule fired inside it: not pure calculation, already reported above

        has_signal = id(node) in decision_functions or bool(CRITICAL_NAME_RE.match(node.name))
        if has_signal:
            hit = _find_terminal_outcome(node)
            if hit:
                n, reason, conf = hit
                # D-324: a single-step function (no loop) doesn't fit the base
                # Outcome set's pipeline/task vocabulary — use the lighter,
                # synchronous-operation field set instead of inventing an 8th
                # decision class.
                if _is_simple_sync_operation(node):
                    make_entry(n, node.name, ["Outcome"], reason, conf,
                               "Synchronous operation resolves to a terminal status",
                               required_fields_override={"Outcome": SIMPLE_OUTCOME_EVIDENCE_FIELDS})
                else:
                    make_entry(n, node.name, ["Outcome"], reason, conf, "Pipeline completes with partial failure")
        elif _is_pure_calculation(node, io_names):
            entries.append(PlacementEntry(
                file=path, line=node.lineno, symbol=node.name,
                decision_classes=[], mandatory_status="no-log",
                recommended_event_name="", recommended_severity="",
                required_fields=[], existing_log_status="n/a", missing_evidence=[],
                classification_confidence=0.9,
                reason="pure calculation — no boundary crossed, no state changed, no outcome established",
                owner=file_owner,
            ))

    return entries


# ── Git file discovery (mirrors log-coverage-check.py for consistency) ─────────

def get_changed_files(pr_mode: bool, staged_mode: bool, base_ref: str) -> list:
    """Python files changed vs. base_ref (PR mode) or currently staged (staged mode)."""
    try:
        if pr_mode:
            base = base_ref or os.environ.get("GITHUB_BASE_REF", "main")
            out = subprocess.check_output(
                ["git", "diff", "--name-only", "--diff-filter=ACM", f"origin/{base}...HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        elif staged_mode:
            out = subprocess.check_output(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        else:
            return []
        return [f for f in out.splitlines() if f.endswith(".py") and Path(f).exists()]
    except subprocess.CalledProcessError:
        return []


def main() -> None:
    """CLI entry point: scan the requested file set and print the placement plan as JSON."""
    parser = argparse.ArgumentParser(description="Raven AST Decision-Point Scanner")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pr", action="store_true")
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--file", default=None)
    parser.add_argument("--base-ref", default=None)
    args = parser.parse_args()

    if args.file:
        files = [args.file] if Path(args.file).exists() else []
        if not files:
            print(f"❌ File not found: {args.file}", file=sys.stderr)
            sys.exit(2)
    else:
        files = get_changed_files(args.pr, args.staged, args.base_ref)

    all_entries = []
    for f in files:
        all_entries.extend(analyze_file(f))

    print(json.dumps([asdict(e) for e in all_entries], indent=2))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠️  ast_decision_scanner: scanner error — {e} (fail-open)", file=sys.stderr)
        sys.exit(2)
