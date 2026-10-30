#!/usr/bin/env python3
"""
Raven — shared logging-rule engine (gap plan M2).

ast_decision_scanner.py (raven-decision-map) and log-coverage-check.py
(raven-applog) each grew their own idea of what must be logged, and they
disagreed: the scanner called `except: pass` around a database call "pure
calculation" while the coverage check flagged it. Both now import the rules
below, so for the same code they report the same rule ids.

Rules (each finding: rule_id, tier mandatory|recommended, line, symbol,
detail, satisfied, opted_out):

  R-SWALLOW     an except block with no raise and no WARN-or-higher log.
                Mandatory for a bare / Exception / BaseException catch, or
                when the try body does I/O; recommended otherwise.
  R-DOWNGRADE   a failure logged only at DEBUG/INFO (and not re-raised).
  R-CLIENT-DEP  method calls on client objects — cursor, conn, session,
                client, engine, pool, producer, consumer, ... — or on a
                parameter typed from an external module, with no dependency
                record (dependency_call()/llm_call(), or a raven_log context
                with dependency_name).
  R-LLM         a call to a model provider (provider SDK imports, Bedrock or
                OCI GenAI clients, a chat/completions endpoint literal) with
                no LLM record (llm_call(), or a raven_log context carrying
                the raven-eval fields).
  R-AI-OUTCOME  a function that returns an AI answer (an answer/completion
                key next to sources/citations, a build_answer-style name, or
                the return of an LLM call) with no ai_outcome() record.
  R-MUTATION    a write: SQL INSERT/UPDATE/DELETE text, SQLAlchemy
                update()/delete()/insert(), session.delete/add/merge, with
                no audit_change() (or change-set) record. UPDATE/DELETE are
                mandatory; inserts and adds recommended.
  R-PARITY      an LLM call site that isn't wrapped by llm_call() while a
                sibling in the same package is — adapters for the same kind
                of provider must write the same field set.

A function is "pure calculation" only when no rule fires inside it.

`# raven: expected <reason>` on a finding's line (or the line above) opts it
out; opted-out findings are still returned (opted_out=True) so they can be
counted.

Also here: the shrink-only baseline helpers the three gates share —
baseline counts per rule per top-level package may only go down unless a
write is given --allow-increase --reason, and every accepted increase is
appended to .raven/baseline-increases.log.

Stdlib only, never raises: evaluate() returns [] for anything it can't read.
"""

import ast
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RULE_IDS = ("R-SWALLOW", "R-DOWNGRADE", "R-CLIENT-DEP", "R-LLM", "R-AI-OUTCOME",
            "R-MUTATION", "R-PARITY")

# What each rule asks the code to record, for the scanners' placement plans.
RULE_DECISION_CLASSES = {
    "R-SWALLOW": ["Recovery"], "R-DOWNGRADE": ["Recovery"],
    "R-CLIENT-DEP": ["Dependency"], "R-LLM": ["Dependency"], "R-PARITY": ["Dependency"],
    "R-AI-OUTCOME": ["Outcome"], "R-MUTATION": ["State Transition"],
}
DEPENDENCY_FIELDS = ["dependency_name", "operation", "duration_ms", "result", "error_class",
                     "attempt", "trace_id"]
EVAL_FIELDS = ["model_version", "prompt_version", "policy_version", "retrieval_document_ids",
               "retrieval_failed", "input_ref", "output_ref"]
AI_OUTCOME_FIELDS = ["retrieval_document_ids", "retrieval_count", "retrieval_failed",
                     "context_truncated", "model_version", "prompt_version", "input_ref",
                     "output_ref"]
CHANGE_SET_FIELDS = ["object_id", "previous_state", "final_state", "change_set_id",
                     "before_hash", "after_hash", "changed_fields", "actor", "approver",
                     "approval_status"]
RULE_REQUIRED_FIELDS = {
    "R-SWALLOW": ["error_class", "error_code", "result"],
    "R-DOWNGRADE": ["error_class", "error_code", "result"],
    "R-CLIENT-DEP": DEPENDENCY_FIELDS,
    "R-LLM": DEPENDENCY_FIELDS + EVAL_FIELDS,
    "R-PARITY": DEPENDENCY_FIELDS + EVAL_FIELDS,
    "R-AI-OUTCOME": AI_OUTCOME_FIELDS,
    "R-MUTATION": CHANGE_SET_FIELDS,
}

STDLIB_MODULES = {
    "os", "sys", "re", "io", "json", "time", "datetime", "math", "random", "itertools",
    "functools", "collections", "typing", "enum", "dataclasses", "abc", "asyncio", "logging",
    "pathlib", "threading", "string", "hashlib", "base64", "uuid", "copy", "contextlib",
    "inspect", "textwrap", "traceback", "warnings", "importlib", "argparse", "decimal",
    "fractions", "statistics", "operator", "heapq", "bisect", "struct", "pickle", "shlex",
    "glob", "fnmatch", "tempfile", "shutil", "gzip", "zipfile", "tarfile", "csv", "html",
    "unicodedata", "secrets", "hmac", "binascii", "codecs", "locale", "pprint", "types",
    "weakref", "queue", "signal", "platform", "getpass", "configparser", "unittest",
    "__future__",
}
CLIENT_TOKENS = ("cursor", "conn", "connection", "session", "client", "engine", "pool",
                 "producer", "consumer", "db", "redis", "channel", "bucket", "s3", "sftp",
                 "smtp", "sock", "socket", "collection", "table", "queue_client", "kafka")
NOT_CLIENT_METHODS = {"get_logger", "getLogger", "info", "debug", "warning", "error",
                      "exception", "critical"}
LLM_MODULE_RE = re.compile(
    r"^(anthropic|openai|cohere|mistralai|groq|together|replicate|ollama|litellm|vertexai|"
    r"google\.generativeai|google\.genai|azure\.ai\.inference|azure\.ai\.openai|"
    r"oci\.generative_ai\w*|langchain\w*|llama_index\w*)(\..+)?$")
LLM_METHOD_CHAINS = ("chat.completions.create", "completions.create", "messages.create",
                     "generate_content", "responses.create", "chat.complete", "invoke_model",
                     "converse", "generate_text")
LLM_URL_RE = re.compile(r"/chat/completions|/v1/messages|:generateContent|/v1/responses|"
                        r"bedrock-runtime|generativelanguage\.googleapis", re.I)
BEDROCK_SERVICE_RE = re.compile(r"^bedrock(-agent)?-runtime$")
ANSWER_KEYS = {"answer", "completion", "reply", "generated_text", "output_text",
               "ai_response", "llm_response", "llm_answer"}
SOURCE_KEYS = {"sources", "citations", "retrieved", "context_documents", "references",
               "source_documents", "chunks"}
ANSWER_NAME_RE = re.compile(r"^(build|generate|compose|make|format|render|produce)_"
                            r"(answer|reply|completion|summary|response)\w*$|^(answer|ask|respond)(_\w+)?$")
SQL_MUTATION_RE = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(insert|update|delete|merge|upsert)\b", re.I)
OPT_OUT_RE = re.compile(r"#\s*raven:\s*expected\b\s*(.*)", re.I)
WARN_METHODS = {"error", "exception", "critical", "warning", "warn", "fatal"}
LOW_METHODS = {"info", "debug"}
LOG_OBJ_RE = re.compile(r"(^|_)(log|logger|logging)$", re.I)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


# ── tree helpers ───────────────────────────────────────────────────────────

def _walk_scope(node):
    """Walk a function/module body without descending into nested defs or
    classes — each of those is its own scope. Only the body: a function's
    decorators and defaults run where it is defined, not when it is called
    (`@router.post("/v1/chat/completions")` is not a model call)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
        stack = list(node.body)
    else:
        stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(child))


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        inner = _dotted(node.func)
        if inner:
            parts.append(inner + "()")
    return ".".join(reversed(parts))


def _base_name(node):
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else ""


def _chain_names(node) -> list:
    names = []
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        if isinstance(node, ast.Attribute):
            names.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            node = node.value
    if isinstance(node, ast.Name):
        names.append(node.id)
    return names


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _str_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.Call) and _call_name(node) == "text" and node.args:
        return _str_value(node.args[0])
    return None


def _dict_keys(node) -> set:
    if not isinstance(node, ast.Dict):
        return set()
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


# ── imports ────────────────────────────────────────────────────────────────

def _imports(tree):
    """(external names -> module, llm names). A name is external when its
    module isn't stdlib and isn't a relative / first-party import."""
    external, llm = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                local = alias.asname or root
                if root not in STDLIB_MODULES:
                    external[local] = alias.name
                if LLM_MODULE_RE.match(alias.name):
                    llm.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            root = node.module.split(".")[0]
            for alias in node.names:
                local = alias.asname or alias.name
                if root not in STDLIB_MODULES:
                    external[local] = node.module
                if LLM_MODULE_RE.match(node.module) or LLM_MODULE_RE.match(f"{node.module}.{alias.name}"):
                    llm.add(local)
    return external, llm


# ── log classification ─────────────────────────────────────────────────────

def _log_level(call: ast.Call):
    """"warn" (WARN or higher, or a level we can't read), "low" (INFO/DEBUG),
    or None when the call isn't a log call."""
    func = call.func
    name = _call_name(call)
    if name == "raven_log" or (isinstance(func, ast.Name) and func.id in ("raven_log",)):
        level = None
        if call.args:
            level = _str_value(call.args[0])
        for kw in call.keywords:
            if kw.arg == "level":
                level = _str_value(kw.value)
        if level is None:
            return "warn"
        return "warn" if level.upper() in ("ERROR", "WARN", "WARNING", "CRITICAL") else "low"
    if isinstance(func, ast.Attribute):
        obj = _base_name(func.value) or (func.value.attr if isinstance(func.value, ast.Attribute) else "")
        if LOG_OBJ_RE.search(obj or "") or obj in ("logging", "_log", "_logger"):
            if func.attr in WARN_METHODS:
                return "warn"
            if func.attr in LOW_METHODS:
                return "low"
    return None


def _helper_calls(scope_nodes) -> set:
    """Names of raven-instrument helpers used in a scope (calls and with-items)."""
    used = set()
    for node in scope_nodes:
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ("dependency_call", "llm_call", "audit_change", "ai_outcome", "boundary",
                        "mcp_tool", "job", "consumer", "wrap_client", "instrumented_transport"):
                used.add(name)
    return used


def _logged_context_keys(scope_nodes) -> set:
    keys = set()
    for node in scope_nodes:
        if isinstance(node, ast.Call) and _call_name(node) in ("raven_log", "log", "boundary_log"):
            for kw in node.keywords:
                if kw.arg == "context":
                    keys |= _dict_keys(kw.value)
    return keys


# ── the per-function facts every rule reads ────────────────────────────────

def _client_call_lines(scope_nodes, external, typed_params):
    lines = []
    for node in scope_nodes:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr in NOT_CLIENT_METHODS or node.func.attr.startswith("_"):
            continue
        chain = [n.lower() for n in _chain_names(node.func.value)]
        if any(LOG_OBJ_RE.search(n) for n in chain):
            continue
        base = _base_name(node.func.value)
        if base in typed_params:
            lines.append(node.lineno)
            continue
        if base in external and external[base].split(".")[0] not in STDLIB_MODULES:
            continue  # a module-level SDK call is the scanners' own Dependency territory
        if any(n == t or n.endswith("_" + t) or n.startswith(t + "_") for n in chain for t in CLIENT_TOKENS):
            lines.append(node.lineno)
    return lines


HTTP_SEND_METHODS = {"post", "request", "send", "urlopen", "stream", "put"}


def _llm_call_lines(scope_nodes, llm_names):
    """Lines where this scope calls a model. An endpoint literal
    (".../chat/completions") only counts when the same scope also sends an
    HTTP request — a function that merely builds the URL isn't the call."""
    scope_nodes = list(scope_nodes)
    sends_http = any(isinstance(n, ast.Call) and _call_name(n) in HTTP_SEND_METHODS for n in scope_nodes)
    lines = []
    for node in scope_nodes:
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            base = _base_name(node.func)
            if base in llm_names or any(dotted.endswith(c) for c in LLM_METHOD_CHAINS):
                lines.append(node.lineno)
                continue
            if _call_name(node) == "client":
                service = [_str_value(a) for a in node.args[:1]] + \
                          [_str_value(k.value) for k in node.keywords if k.arg == "service_name"]
                if any(s and BEDROCK_SERVICE_RE.match(s) for s in service):
                    lines.append(node.lineno)
                    continue
            if "generative_ai" in dotted.lower() and "inference" in dotted.lower():
                lines.append(node.lineno)
        elif sends_http and isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and LLM_URL_RE.search(node.value):
            lines.append(getattr(node, "lineno", 0))
    return lines


ANSWERISH_KEYS = ANSWER_KEYS | SOURCE_KEYS | {"content", "text", "message", "response", "output",
                                              "result", "summary", "choices"}


def _could_carry_an_answer(value) -> bool:
    """A returned value that might be model output: anything but a constant
    or a literal dict whose keys are all clearly not an answer (a probe's
    {"classified": 3, "p95_ms": 120})."""
    if isinstance(value, ast.Constant):
        return False
    if isinstance(value, ast.Dict):
        keys = _dict_keys(value)
        return len(keys) < len(value.keys) or bool(keys & ANSWERISH_KEYS)
    return True


def _returns_ai_answer(func, scope_nodes, calls_llm) -> bool:
    returns = [n for n in scope_nodes if isinstance(n, ast.Return) and n.value is not None]
    for ret in returns:
        keys = _dict_keys(ret.value)
        if keys & ANSWER_KEYS or (keys & SOURCE_KEYS and keys & {"response", "summary", "text"}):
            return True
    if calls_llm and any(_could_carry_an_answer(r.value) for r in returns):
        return True
    return bool(ANSWER_NAME_RE.match(func.name)) and bool(returns)


def _mutations(scope_nodes, external):
    """[(line, mandatory?, what)]."""
    found = []
    sqlalchemy_names = {n for n, mod in external.items() if mod.split(".")[0] in ("sqlalchemy", "sqlmodel")}
    for node in scope_nodes:
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in ("execute", "executemany", "exec_driver_sql", "executescript") and node.args:
            sql = _str_value(node.args[0])
            m = SQL_MUTATION_RE.match(sql or "")
            if m:
                verb = m.group(1).lower()
                found.append((node.lineno, verb in ("update", "delete", "merge", "upsert"), f"SQL {verb.upper()}"))
        elif isinstance(node.func, ast.Name) and node.func.id in ("update", "delete", "insert") \
                and node.func.id in sqlalchemy_names:
            found.append((node.lineno, node.func.id != "insert", f"SQLAlchemy {node.func.id}()"))
        elif isinstance(node.func, ast.Attribute) and name in ("delete", "add", "add_all", "merge", "bulk_save_objects"):
            chain = [n.lower() for n in _chain_names(node.func.value)]
            if any(n in ("session", "db", "sess") or n.endswith("_session") for n in chain):
                found.append((node.lineno, name == "delete", f"session.{name}()"))
    return found


def _handler_type_names(handler) -> list:
    t = handler.type
    if t is None:
        return []
    elts = t.elts if isinstance(t, ast.Tuple) else [t]
    return [_dotted(e).split(".")[-1] for e in elts]


def _try_does_io(try_node, external, llm_names) -> bool:
    for stmt in try_node.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                base = _base_name(node.func)
                chain = [n.lower() for n in _chain_names(node.func)]
                if base in external or base in llm_names or base in ("open", "urlopen", "subprocess"):
                    return True
                if _call_name(node) in ("urlopen", "open", "run", "check_output", "Popen", "connect", "send", "recv"):
                    return True
                if any(n == t or n.endswith("_" + t) for n in chain for t in CLIENT_TOKENS):
                    return True
            if isinstance(node, ast.Await):
                return True
    return False


def _opt_out(lines: list, lineno: int):
    for ln in (lineno, lineno - 1, lineno + 1):
        if 1 <= ln <= len(lines):
            m = OPT_OUT_RE.search(lines[ln - 1])
            if m:
                return m.group(1).strip() or "expected"
    return None


# ── evaluation ─────────────────────────────────────────────────────────────

def _finding(rule_id, tier, line, symbol, detail, satisfied, lines, function_line=0, extra=None):
    reason = _opt_out(lines, line)
    out = {"rule_id": rule_id, "tier": tier, "line": line, "symbol": symbol, "detail": detail,
           "satisfied": satisfied, "opted_out": reason is not None, "opt_out_reason": reason or "",
           "function_line": function_line}
    if extra:
        out.update(extra)
    return out


def _handler_findings(scope, symbol, function_line, external, llm_names, lines):
    out = []
    for node in _walk_scope(scope):
        if not isinstance(node, ast.Try):
            continue
        only_imports = all(isinstance(s, (ast.Import, ast.ImportFrom)) for s in node.body)
        does_io = _try_does_io(node, external, llm_names)
        for handler in node.handlers:
            types = _handler_type_names(handler)
            if only_imports and set(types) <= {"ImportError", "ModuleNotFoundError"} and types:
                continue  # optional dependency, not a failure path
            body_nodes = [n for stmt in handler.body for n in ast.walk(stmt)]
            if any(isinstance(n, ast.Raise) for n in body_nodes):
                continue
            levels = {_log_level(n) for n in body_nodes if isinstance(n, ast.Call)} - {None}
            if "warn" in levels:
                continue
            broad = not types or bool({"Exception", "BaseException"} & set(types))
            tier = "mandatory" if (broad or does_io) else "recommended"
            caught = ", ".join(types) or "everything"
            if levels == {"low"}:
                out.append(_finding("R-DOWNGRADE", tier, handler.lineno, symbol,
                                    f"except ({caught}) logs the failure only at DEBUG/INFO",
                                    False, lines, function_line))
            else:
                out.append(_finding("R-SWALLOW", tier, handler.lineno, symbol,
                                    f"except ({caught}) swallows the error: no raise and no "
                                    f"WARN-or-higher log", False, lines, function_line))
    return out


def _function_findings(func, external, llm_names, lines):
    scope_nodes = list(_walk_scope(func))
    helpers = _helper_calls(scope_nodes) | {
        _call_name(d) if isinstance(d, ast.Call) else _dotted(d).split(".")[-1]
        for d in func.decorator_list}
    logged = _logged_context_keys(scope_nodes)
    typed_params = set()
    for arg in list(func.args.args) + list(func.args.kwonlyargs):
        if arg.annotation is not None and _base_name(arg.annotation) in external:
            typed_params.add(arg.arg)
    out = []
    sym, fl = func.name, func.lineno

    llm_lines = _llm_call_lines(scope_nodes, llm_names)
    calls_llm = bool(llm_lines)

    # A model call's LLM record already carries every Dependency field, so a
    # function that calls a model is R-LLM's, not R-CLIENT-DEP's as well; and
    # a client call that IS a write (session.delete, an UPDATE) is R-MUTATION's.
    mutations = _mutations(scope_nodes, external)
    mutation_lines = {line for line, _, _ in mutations}
    client_lines = [] if calls_llm else [
        line for line in _client_call_lines(scope_nodes, external, typed_params) if line not in mutation_lines]
    if client_lines:
        ok = bool(helpers & {"dependency_call", "llm_call", "wrap_client", "instrumented_transport"}) \
            or "dependency_name" in logged
        out.append(_finding("R-CLIENT-DEP", "recommended", fl, sym,
                            f"calls a client object (line {client_lines[0]}) with no dependency record",
                            ok, lines, fl))

    if calls_llm:
        wrapped = "llm_call" in helpers
        ok = wrapped or set(EVAL_FIELDS) <= logged
        out.append(_finding("R-LLM", "mandatory", fl, sym,
                            f"calls a model provider (line {llm_lines[0]}) with no LLM record",
                            ok, lines, fl, {"wrapped": wrapped, "logged_keys": sorted(logged)}))

    if _returns_ai_answer(func, scope_nodes, calls_llm):
        ok = "ai_outcome" in helpers or {"retrieval_document_ids", "retrieval_failed"} <= logged
        out.append(_finding("R-AI-OUTCOME", "mandatory", fl, sym,
                            "returns an AI answer with no ai_outcome() record (retrieval evidence)",
                            ok, lines, fl))

    if mutations:
        ok = "audit_change" in helpers or "change_set_id" in logged or \
            {"previous_state", "final_state"} <= logged
        mandatory = any(m for _, m, _ in mutations)
        first = mutations[0]
        out.append(_finding("R-MUTATION", "mandatory" if mandatory else "recommended", fl, sym,
                            f"{first[2]} (line {first[0]}) with no audit_change() record",
                            ok, lines, fl))
    return out


_parity_cache = {}


def _package_llm_sites(directory: Path) -> list:
    """[(file, function, wrapped)] for every LLM call site in a package dir."""
    key = str(directory)
    if key in _parity_cache:
        return _parity_cache[key]
    sites = []
    for path in _safe(lambda: sorted(directory.glob("*.py")), []) or []:
        source = _safe(lambda: path.read_text(encoding="utf-8", errors="replace"))
        tree = _safe(lambda: ast.parse(source or ""))
        if tree is None:
            continue
        external, llm_names = _imports(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scope_nodes = list(_walk_scope(node))
                if _llm_call_lines(scope_nodes, llm_names):
                    sites.append((str(path), node.name, "llm_call" in _helper_calls(scope_nodes)))
    _parity_cache[key] = sites
    return sites


def evaluate(tree, source: str, path: str = "") -> list:
    """Every rule finding in one parsed file (satisfied and opted-out ones
    included — callers filter). Never raises."""
    try:
        lines = (source or "").splitlines()
        external, llm_names = _imports(tree)
        findings = _handler_findings(tree, "<module>", 0, external, llm_names, lines)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                findings += _handler_findings(node, node.name, node.lineno, external, llm_names, lines)
                findings += _function_findings(node, external, llm_names, lines)
        if path:
            siblings = _package_llm_sites(Path(path).resolve().parent)
            if any(wrapped for _, _, wrapped in siblings):
                for f in [f for f in findings if f["rule_id"] == "R-LLM" and not f.get("wrapped")]:
                    findings.append(_finding("R-PARITY", "mandatory", f["line"], f["symbol"],
                                             "LLM call site not wrapped by llm_call() while a sibling "
                                             "adapter in this package is — its records won't match",
                                             False, lines, f["function_line"]))
        findings.sort(key=lambda f: (f["line"], f["rule_id"]))
        return findings
    except Exception:
        return []


def open_findings(findings: list) -> list:
    """The ones that still need code: not satisfied, not opted out."""
    return [f for f in findings if not f.get("satisfied") and not f.get("opted_out")]


def evaluate_path(path: str) -> list:
    source = _safe(lambda: Path(path).read_text(encoding="utf-8", errors="replace"))
    tree = _safe(lambda: ast.parse(source or "", filename=path))
    return evaluate(tree, source or "", path) if tree is not None else []


# ── shrink-only baselines (shared by the three gates) ──────────────────────

INCREASE_LOG = Path(".raven") / "baseline-increases.log"


def count_key(entry: dict) -> str:
    """The rule a baselined finding counts toward: its rule id, else its first
    decision class, else its kind (the emitter/API-log gates' findings)."""
    if entry.get("rule_id"):
        return entry["rule_id"]
    classes = entry.get("decision_classes") or []
    if classes:
        return "class:" + classes[0]
    return entry.get("kind") or "finding"


def package_of(file_path) -> str:
    parts = Path(str(file_path or "")).parts
    return parts[0] if len(parts) > 1 else "."


def baseline_counts(entries: list) -> dict:
    counts = {}
    for entry in entries:
        rule = count_key(entry)
        pkg = package_of(entry.get("file"))
        counts.setdefault(rule, {})
        counts[rule][pkg] = counts[rule].get(pkg, 0) + 1
    return counts


def increases(old: dict, new: dict) -> list:
    """[(rule, package, before, after)] wherever `new` has more than `old`."""
    out = []
    for rule, pkgs in sorted(new.items()):
        for pkg, n in sorted(pkgs.items()):
            before = (old.get(rule) or {}).get(pkg, 0)
            if n > before:
                out.append((rule, pkg, before, n))
    return out


def _git_user() -> str:
    return (_safe(lambda: subprocess.run(["git", "config", "user.email"], capture_output=True,
                                         text=True, timeout=5).stdout.strip(), "") or
            os.environ.get("USER", "") or "unknown")


def guard_write(gate: str, old_counts: dict, new_counts: dict, allow_increase: bool,
                reason: str, log_path: Path = INCREASE_LOG):
    """(allowed, message). A write that raises any count is refused unless
    allow_increase and a non-empty reason are given; an accepted increase is
    appended to log_path (who, when, which counts, why). old_counts=None
    means there is no baseline yet: the first write establishes it."""
    if old_counts is None:
        return True, ""
    grown = increases(old_counts, new_counts)
    if not grown:
        return True, ""
    listing = "; ".join(f"{rule} in {pkg}: {before} -> {after}" for rule, pkg, before, after in grown[:12])
    if len(grown) > 12:
        listing += f"; (+{len(grown) - 12} more)"
    if not (allow_increase and (reason or "").strip()):
        return False, (f"{gate}: refusing to write a baseline that grows ({listing}). Baselines only "
                       f"shrink: fix the new findings, or rerun with --allow-increase --reason \"<why>\".")
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "gate": gate, "by": _git_user(),
             "reason": reason.strip(), "increases": [list(g) for g in grown]}
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    return True, f"{gate}: baseline grows ({listing}); accepted: {reason.strip()}"


if __name__ == "__main__":
    import sys
    for target in sys.argv[1:]:
        for f in open_findings(evaluate_path(target)):
            print(f"{target}:{f['line']}: {f['rule_id']} [{f['tier']}] {f['symbol']} — {f['detail']}")
