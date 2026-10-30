#!/usr/bin/env python3
"""
Raven — PR Comment Poster v1.0 (task T15)
Posts raven-decision-map findings as inline PR review comments, following the
format defined in auto-log-guardrail-plugin-pr-comment-format.md (task T13).
A finding whose line isn't part of the diff (raven-refresh's "legacy debt")
rolls into one summary comment instead of an inline one. Idempotent: a
re-run on a new commit updates the existing summary comment and adds/removes
inline comments to match the current finding set, rather than duplicating.

Stdlib only (urllib), consistent with the other raven-core scripts — no
extra dependency for a CI-only utility.

Requires (GitHub):
    GITHUB_TOKEN        — repo-scoped token (Actions provides this natively)
    --repo / GITHUB_REPOSITORY   — "owner/repo"
    --commit-sha / GITHUB_SHA    — the PR head commit inline comments attach to
    --pr-number                  — the PR number

Requires (Azure Repos — summary thread only):
    AZURE_DEVOPS_EXT_PAT or SYSTEM_ACCESSTOKEN
    --url or SYSTEM_PULLREQUEST_URL / SYSTEM_COLLECTIONURI + SYSTEM_TEAMPROJECT
    + BUILD_REPOSITORY_NAME + SYSTEM_PULLREQUEST_PULLREQUESTID

Usage:
    python3 ast_decision_scanner.py --pr | python3 post-scan-comments.py --pr-number 42
    python3 post-scan-comments.py --pr-number 42 --findings findings.json

Exit codes: 0 = posted (or nothing to post) | 2 = usage/config/API error (fail-open —
never blocks the PR itself; see T01, this is a reporting step, not the gate)
"""

import argparse, base64, json, os, re, subprocess, sys
import urllib.parse, urllib.request, urllib.error
from pathlib import Path
from typing import Optional

MARKER_RE = re.compile(r"<!-- raven-decision-map:(finding|summary):?([^\s>]*) -->")

STATUS_ICON = {"mandatory": "❌", "recommended": "⚠️", "diagnostic-only": "ℹ️"}
STATUS_LABEL = {"mandatory": "Required", "recommended": "Recommended", "diagnostic-only": "Diagnostic"}


# ── Diff-hunk parsing — which lines are inline-attachable ───────────────────────

def get_diff_hunks(base_ref: str) -> dict:
    """
    Map file path -> set of added line numbers (in the new file) that are part
    of the diff. GitHub only accepts an inline comment on a line within the
    diff context; using `--unified=0` and only counting added lines is a
    conservative simplification — it will not offer inline placement on an
    unchanged context line even though GitHub would sometimes accept one.
    Fail-open on any git error: an empty map means everything routes to the
    summary comment instead of inline, never a scan failure.
    """
    try:
        try:
            out = subprocess.check_output(
                ["git", "diff", "--unified=0", f"origin/{base_ref}...HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", "replace")
        except subprocess.CalledProcessError:
            out = subprocess.check_output(
                ["git", "diff", "--unified=0", f"{base_ref}...HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", "replace")
    except subprocess.CalledProcessError:
        return {}

    hunks = {}
    current_file = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current_file = None if path == "/dev/null" else path[2:] if path.startswith("b/") else path
            if current_file:
                hunks.setdefault(current_file, set())
        elif line.startswith("@@") and current_file:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                hunks[current_file].update(range(start, start + max(count, 1)))
    return hunks


# ── Finding categorization (task T13's inline-vs-legacy split) ──────────────────

def categorize_findings(findings: list, diff_hunks: dict) -> tuple:
    """Split into (inline-attachable, legacy/off-diff, flood_risk_count).
    no-log findings are dropped entirely — never posted, per T13."""
    inline, legacy = [], []
    flood_count = 0
    for f in findings:
        if f.get("mandatory_status") == "no-log":
            continue
        in_diff = f["line"] in diff_hunks.get(f["file"], set())
        if not f.get("decision_classes"):
            flood_count += 1
            if in_diff:
                inline.append(f)
            continue
        (inline if in_diff else legacy).append(f)
    return inline, legacy, flood_count


# ── Comment body formatting (task T13's templates) ──────────────────────────────

def format_inline_comment(finding: dict) -> str:
    marker = f"<!-- raven-decision-map:finding:{finding['file']}:{finding['line']} -->"

    if not finding.get("decision_classes"):
        return (
            "**⚠️ Possible log flooding**\n\n"
            f"{finding['reason']}\n\n"
            "See raven-flood for remediation — this does not block the gate on its own, "
            "and any proposed removal goes through raven-flood's removal-candidate flow, "
            f"never an automatic deletion.\n\n{marker}"
        )

    icon = STATUS_ICON.get(finding["mandatory_status"], "ℹ️")
    label = STATUS_LABEL.get(finding["mandatory_status"], "Diagnostic")
    classes = " / ".join(finding["decision_classes"])

    if finding.get("existing_log_status") == "sufficient":
        evidence_body = "✅ already present"
    else:
        evidence_body = "\n".join(f"- `{field}`" for field in finding.get("missing_evidence", [])) or "(none listed)"

    n = len(finding.get("required_fields", []))
    owner_line = f"\nRouted to: {finding['owner']}" if finding.get("owner") else ""
    cost_benefit = finding.get("cost_benefit", "")

    return (
        f"**{icon} {label}** — {classes}\n\n"
        f"{finding['reason']}\n\n"
        f"<details>\n<summary>Required evidence ({n} field{'s' if n != 1 else ''})</summary>\n\n"
        f"{evidence_body}\n\n</details>\n\n"
        f"{cost_benefit}\n\n"
        f"`recommended_event_name`: `{finding.get('recommended_event_name', '')}` · "
        f"severity `{finding.get('recommended_severity', '')}`{owner_line}\n\n{marker}"
    )


def format_summary_comment(inline_findings: list, legacy_findings: list, flood_count: int) -> str:
    all_findings = inline_findings + legacy_findings
    mandatory = sum(1 for f in all_findings if f["mandatory_status"] == "mandatory")
    recommended = sum(1 for f in all_findings if f["mandatory_status"] == "recommended")
    diagnostic = sum(1 for f in all_findings if f["mandatory_status"] == "diagnostic-only")
    icon = "❌" if mandatory else "✅"

    lines = ["## Raven Decision-Map Scan", "",
              f"{icon} {mandatory} required · {recommended} recommended · {diagnostic} diagnostic", ""]

    if any(f["mandatory_status"] == "mandatory" for f in inline_findings):
        lines += ["**Blocking findings posted as inline comments below.**", ""]

    if legacy_findings:
        lines += [
            f"<details>\n<summary>Legacy findings on unchanged lines ({len(legacy_findings)}) — "
            "visible, not blocking</summary>",
            "", "| File | Line | Class | Status |", "|---|---|---|---|",
        ]
        for f in legacy_findings:
            classes = " / ".join(f["decision_classes"]) or "-"
            lines.append(f"| {f['file']} | {f['line']} | {classes} | {f['mandatory_status']} |")
        lines += ["", "</details>", ""]

    if flood_count:
        lines.append(f"⚠️ {flood_count} log call(s) inside loops flagged — see raven-flood.")

    lines += ["", "<!-- raven-decision-map:summary -->"]
    return "\n".join(lines)


# ── GitHub API (stdlib urllib — no extra dependency) ────────────────────────────

def _api_request(method: str, url: str, token: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw.decode()) if raw else {}


def list_review_comments(repo: str, pr_number: int, token: str) -> list:
    return _api_request("GET", f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments", token)


def list_issue_comments(repo: str, pr_number: int, token: str) -> list:
    return _api_request("GET", f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments", token)


def post_inline_comment(repo: str, pr_number: int, token: str, commit_sha: str, finding: dict, body: str) -> dict:
    return _api_request("POST", f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments", token, {
        "body": body, "commit_id": commit_sha, "path": finding["file"],
        "line": finding["line"], "side": "RIGHT",
    })


def delete_review_comment(repo: str, comment_id, token: str) -> None:
    _api_request("DELETE", f"https://api.github.com/repos/{repo}/pulls/comments/{comment_id}", token)


_ADO_PR_RE = re.compile(
    r"(?:https?://)?dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)/pullrequests?/(\d+)",
    re.IGNORECASE)
_ADO_VS_PR_RE = re.compile(
    r"(?:https?://)?([^.]+)\.visualstudio\.com(?:/DefaultCollection)?/"
    r"([^/]+)/_git/([^/]+)/pullrequests?/(\d+)",
    re.IGNORECASE)
_ADO_REST_PR_RE = re.compile(
    r"(?:https?://)?dev\.azure\.com/([^/]+)/([^/]+)/_apis/git/repositories/"
    r"([^/]+)/pullRequests/(\d+)",
    re.IGNORECASE)


def parse_ado_pr_url(url: str) -> Optional[dict]:
    text = (url or "").strip()
    m = _ADO_PR_RE.search(text)
    if m:
        return {"ado_org": m.group(1), "project": m.group(2),
                "repo": m.group(3), "pr_id": int(m.group(4))}
    m = _ADO_VS_PR_RE.search(text)
    if m:
        return {"ado_org": m.group(1), "project": m.group(2),
                "repo": m.group(3), "pr_id": int(m.group(4))}
    m = _ADO_REST_PR_RE.search(text)
    if m:
        return {"ado_org": m.group(1), "project": m.group(2),
                "repo": m.group(3), "pr_id": int(m.group(4))}
    return None


def ado_from_env() -> Optional[dict]:
    parsed = parse_ado_pr_url(os.environ.get("SYSTEM_PULLREQUEST_URL") or "")
    if parsed:
        return parsed
    collection = os.environ.get("SYSTEM_COLLECTIONURI") or ""
    org = ""
    m = re.search(r"dev\.azure\.com/([^/]+)", collection, re.I)
    if m:
        org = m.group(1)
    else:
        m = re.search(r"https?://([^.]+)\.visualstudio\.com", collection, re.I)
        if m:
            org = m.group(1)
    project = os.environ.get("SYSTEM_TEAMPROJECT") or ""
    repo = os.environ.get("BUILD_REPOSITORY_NAME") or ""
    pr = os.environ.get("SYSTEM_PULLREQUEST_PULLREQUESTID") or ""
    if org and project and repo and pr.isdigit():
        return {"ado_org": org, "project": project, "repo": repo, "pr_id": int(pr)}
    return None


def _ado_api(method: str, url: str, token: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    auth = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw.decode()) if raw else {}


def upsert_ado_summary_comment(parsed: dict, token: str, body: str) -> dict:
    marker = "<!-- raven-decision-map:summary -->"
    org = urllib.parse.quote(parsed["ado_org"], safe="")
    project = urllib.parse.quote(parsed["project"], safe="")
    repo = urllib.parse.quote(parsed["repo"], safe="")
    pr_id = parsed["pr_id"]
    threads_url = (
        f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}"
        f"/pullRequests/{pr_id}/threads?api-version=7.1")
    existing = _ado_api("GET", threads_url, token)
    for thread in existing.get("value") or []:
        for c in thread.get("comments") or []:
            if marker in (c.get("content") or ""):
                tid, cid = thread.get("id"), c.get("id")
                patch_url = (
                    f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/"
                    f"{repo}/pullRequests/{pr_id}/threads/{tid}/comments/{cid}"
                    f"?api-version=7.1")
                return _ado_api("PATCH", patch_url, token, {"content": body})
    return _ado_api("POST", threads_url, token, {
        "comments": [{"parentCommentId": 0, "content": body, "commentType": 1}],
        "status": 1,
    })


def upsert_summary_comment(repo: str, pr_number: int, token: str, body: str) -> dict:
    marker = "<!-- raven-decision-map:summary -->"
    for c in list_issue_comments(repo, pr_number, token):
        if not isinstance(c, dict):
            continue
        if marker in c.get("body", ""):
            return _api_request("PATCH", f"https://api.github.com/repos/{repo}/issues/comments/{c['id']}",
                                 token, {"body": body})
    return _api_request("POST", f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
                         token, {"body": body})


def sync_inline_comments(repo: str, pr_number: int, token: str, commit_sha: str, findings: list) -> tuple:
    """Post new inline comments for findings not already commented on; delete
    existing raven-decision-map inline comments whose finding no longer
    exists (fixed or removed since the last run). Returns (posted, deleted)."""
    existing_by_key = {}
    for c in list_review_comments(repo, pr_number, token):
        m = MARKER_RE.search(c.get("body", ""))
        if m and m.group(1) == "finding":
            existing_by_key[m.group(2)] = c["id"]

    current_keys = set()
    posted = 0
    for f in findings:
        key = f"{f['file']}:{f['line']}"
        current_keys.add(key)
        if key not in existing_by_key:
            post_inline_comment(repo, pr_number, token, commit_sha, f, format_inline_comment(f))
            posted += 1

    deleted = 0
    for key, comment_id in existing_by_key.items():
        if key not in current_keys:
            delete_review_comment(repo, comment_id, token)
            deleted += 1

    return posted, deleted


# ── Entry point ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Raven PR Comment Poster")
    parser.add_argument("--pr-number", type=int, default=None)
    parser.add_argument("--findings", default=None, help="Path to scanner JSON; reads stdin if omitted")
    parser.add_argument("--base-ref", default=None)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--commit-sha", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument("--url", default=os.environ.get("SYSTEM_PULLREQUEST_URL") or "")
    args = parser.parse_args()

    ado = parse_ado_pr_url(args.url) or ado_from_env()
    if ado:
        token = (os.environ.get("AZURE_DEVOPS_EXT_PAT")
                 or os.environ.get("SYSTEM_ACCESSTOKEN")
                 or os.environ.get("GITHUB_TOKEN") or "")
        if not token:
            print("❌ AZURE_DEVOPS_EXT_PAT / SYSTEM_ACCESSTOKEN not set", file=sys.stderr)
            sys.exit(2)
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print("❌ GITHUB_TOKEN not set", file=sys.stderr)
            sys.exit(2)
        if not args.repo:
            print("❌ --repo or GITHUB_REPOSITORY is required", file=sys.stderr)
            sys.exit(2)
        if not args.commit_sha:
            print("❌ --commit-sha or GITHUB_SHA is required", file=sys.stderr)
            sys.exit(2)
        if args.pr_number is None:
            print("❌ --pr-number is required for GitHub", file=sys.stderr)
            sys.exit(2)

    raw = Path(args.findings).read_text() if args.findings else sys.stdin.read()
    findings = json.loads(raw) if raw.strip() else []

    diff_hunks = get_diff_hunks(args.base_ref or os.environ.get("GITHUB_BASE_REF", "main"))
    inline, legacy, flood_count = categorize_findings(findings, diff_hunks)
    summary = format_summary_comment(inline, legacy, flood_count)

    if ado:
        upsert_ado_summary_comment(ado, token, summary)
        print(f"Posted Azure Repos summary thread ({len(inline)} inline finding(s) "
              f"rolled into the summary — ADO has no GitHub-style inline review comments).")
        return

    posted, deleted = sync_inline_comments(args.repo, args.pr_number, token, args.commit_sha, inline)
    upsert_summary_comment(args.repo, args.pr_number, token, summary)

    print(f"Posted {posted} new inline comment(s), removed {deleted} resolved one(s), "
          f"{len(legacy)} legacy finding(s) rolled into the summary.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"⚠️  GitHub API error: {e.code} {e.reason} (fail-open — not blocking the PR)", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"⚠️  post-scan-comments: unexpected error — {e} (fail-open)", file=sys.stderr)
        sys.exit(2)
