"""Bitbucket Cloud client — fetches commits, diffs, and file contents for a Jira ticket."""

import re
import requests
from dataclasses import dataclass
from qbot.config import config

# Max size per diff to avoid blowing up the context
_MAX_DIFF_CHARS = 10_000
_MAX_TOTAL_CONTEXT = 30_000
_MAX_COMMITS = 10

# File patterns to SKIP in diffs (not useful for test generation)
_SKIP_PATTERNS = {
    ".min.js", ".min.css", ".map", ".lock", ".svg", ".png", ".jpg",
    ".gif", ".ico", ".woff", ".ttf", ".eot", ".pdf",
    "package-lock.json", "yarn.lock", ".csproj", ".sln",
    "node_modules/", "bin/", "obj/", "dist/", "build/",
    "migrations/", "Migration",
}

# Regex patterns for merge/sync commits to skip (no useful code changes)
_MERGE_RE = re.compile(
    r'^\s*('
    r'Merged?\s+in\s+'            # "Merged in feature/..."
    r'|Merge\s+branch\s+'         # "Merge branch 'x' into y"
    r'|Merge\s+pull\s+request'    # "Merge pull request #N"
    r'|Merge\s+remote[- ]tracking'  # "Merge remote-tracking branch"
    r')',
    re.IGNORECASE,
)


@dataclass
class CodeChange:
    """Represents code changes associated with a ticket."""
    commits: list  # [{hash, message, date, author}]
    diffs: list    # [{commit, message, diff_text}]
    summary: str   # human-readable summary for logging


class BitbucketClient:
    """Fetches code changes from Bitbucket Cloud for a given Jira ticket key."""

    def __init__(self, on_log=None):
        self.base_url = "https://api.bitbucket.org/2.0"
        self.workspace = config.bitbucket_workspace
        self.repo_slug = config.bitbucket_repo
        self._log = on_log or (lambda msg: None)

    def _repo_url(self, path: str = "") -> str:
        return f"{self.base_url}/repositories/{self.workspace}/{self.repo_slug}{path}"

    def _get(self, url: str, **kwargs) -> requests.Response:
        # Atlassian scoped API tokens use Basic auth (email:token), not Bearer
        resp = requests.get(
            url,
            auth=(config.jira_username, config.bitbucket_api_token),
            timeout=30,
            **kwargs,
        )
        resp.raise_for_status()
        return resp

    def is_configured(self) -> bool:
        """Check if Bitbucket workspace, repo, and API token are configured."""
        return bool(self.workspace and self.repo_slug and config.bitbucket_api_token)

    def get_ticket_changes(self, ticket_key: str) -> CodeChange:
        """Fetch all code changes for a Jira ticket key (e.g. PDM-1234)."""
        if not self.is_configured():
            return CodeChange([], [], [], "Bitbucket not configured — skipped code fetch.")

        self._log(f"   Searching Bitbucket for commits mentioning {ticket_key}...")

        # Find commits by scanning recent history for the ticket key
        commits = self._find_commits_by_message(ticket_key)

        if not commits:
            # Also try finding PRs with the ticket key
            pr_commits = self._find_commits_via_prs(ticket_key)
            commits = pr_commits

        if not commits:
            return CodeChange([], [], f"No commits found for {ticket_key}.")

        self._log(f"   Found {len(commits)} commit(s) for {ticket_key}")

        # Get diffs — filter to only relevant code files
        diffs = []
        changed_files = 0
        total_chars = 0

        for commit in commits[:_MAX_COMMITS]:
            if total_chars > _MAX_TOTAL_CONTEXT:
                break
            diff_text = self._get_commit_diff(commit["hash"])
            if diff_text:
                filtered = self._filter_diff(diff_text)
                if not filtered.strip():
                    continue
                truncated = filtered[:_MAX_DIFF_CHARS]
                diffs.append({
                    "commit": commit["hash"][:8],
                    "message": commit["message"].split("\n")[0],
                    "diff_text": truncated,
                })
                total_chars += len(truncated)
                changed_files += filtered.count("diff --git")

        summary = (
            f"Found {len(commits)} commit(s), {len(diffs)} diff(s), "
            f"{changed_files} file(s) for {ticket_key} "
            f"({total_chars:,} chars of code context)"
        )
        self._log(f"   {summary}")

        return CodeChange(
            commits=[{
                "hash": c["hash"][:8],
                "message": c["message"].split("\n")[0],
                "date": c.get("date", ""),
                "author": c.get("author", {}).get("raw", ""),
            } for c in commits],
            diffs=diffs,
            summary=summary,
        )

    def _find_commits_by_message(self, ticket_key: str) -> list:
        """Scan recent commits for the ticket key in the commit message."""
        commits = []
        url = self._repo_url("/commits")
        pages = 0
        max_pages = 5  # scan up to ~150 commits

        while url and pages < max_pages:
            try:
                resp = self._get(url)
                data = resp.json()
            except Exception as e:
                self._log(f"   Warning: commit search page {pages + 1} failed: {e}")
                break

            for entry in data.get("values", []):
                msg = entry.get("message", "")
                # Match ticket key (case-insensitive) as a whole word
                if re.search(rf'\b{re.escape(ticket_key)}\b', msg, re.IGNORECASE):
                    # Skip merge/sync commits — they contain no actual code changes
                    if _MERGE_RE.search(msg):
                        continue
                    commits.append(entry)

            url = data.get("next")
            pages += 1

        return commits

    def _find_commits_via_prs(self, ticket_key: str) -> list:
        """Find commits via pull requests that mention the ticket key."""
        try:
            url = self._repo_url("/pullrequests")
            resp = self._get(url, params={
                "q": f'title ~ "{ticket_key}"',
                "state": "MERGED",
                "pagelen": 5,
            })
            data = resp.json()
        except Exception:
            return []

        commits = []
        for pr in data.get("values", []):
            pr_id = pr.get("id")
            try:
                commits_url = self._repo_url(f"/pullrequests/{pr_id}/commits")
                resp = self._get(commits_url)
                pr_commits = resp.json().get("values", [])
                commits.extend(pr_commits)
            except Exception:
                continue

        return commits

    def _get_commit_diff(self, commit_hash: str) -> str:
        """Get the unified diff for a specific commit."""
        try:
            url = self._repo_url(f"/diff/{commit_hash}")
            resp = self._get(url)
            return resp.text
        except Exception:
            return ""

    @staticmethod
    def _filter_diff(diff_text: str) -> str:
        """Remove diff sections for non-code files (binaries, configs, locks, etc.)."""
        sections = re.split(r'(?=^diff --git )', diff_text, flags=re.MULTILINE)
        kept = []
        for section in sections:
            if not section.strip():
                continue
            # Extract file path from "diff --git a/path b/path"
            m = re.match(r'diff --git a/(.+?) b/', section)
            if m:
                path = m.group(1).lower()
                if any(skip in path for skip in _SKIP_PATTERNS):
                    continue
            kept.append(section)
        return "\n".join(kept)


def format_code_context(changes: CodeChange) -> str:
    """Format code changes into a text block suitable for the AI prompt."""
    if not changes.commits:
        return ""

    parts = []
    parts.append("## CODE CHANGES (from Bitbucket commits linked to this ticket)")
    parts.append(f"Commits: {len(changes.commits)}")
    parts.append("")

    # Commit list
    parts.append("### Commits")
    for c in changes.commits:
        parts.append(f"  - {c['hash']} | {c['message']}")
    parts.append("")

    # Diffs (the key context for understanding what changed)
    if changes.diffs:
        parts.append("### Diffs (what was changed)")
        for d in changes.diffs:
            parts.append(f"--- Commit {d['commit']}: {d['message']} ---")
            parts.append(d["diff_text"])
            parts.append("")

    return "\n".join(parts)
