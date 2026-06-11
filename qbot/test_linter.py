"""Deterministic linter for AI-generated Playwright test code.

Catches the failure patterns the system prompt forbids — but enforced in
code instead of hoping the model complied:

  - expect(page).to_have_title(...)            → always breaks on title suffixes
  - expect(page).to_have_url("/relative")      → compares against FULL URL
  - to_have_count(N) with a guessed N          → page has pre-existing items
  - #id / [name=] selectors not present in the crawled DOM snapshots
  - text= / get_by_text strings never seen in the crawled pages
  - .check()/.is_checked() on ids that the snapshots show are NOT native inputs

Issues are returned as structured dicts. "error" severity = definitely wrong,
"warning" severity = suspicious, needs AI verification against the DOM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class LintIssue:
    line: int
    severity: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] line {self.line}: {self.message}"


class SnapshotIndex:
    """Index of everything the crawler actually saw, for selector validation."""

    def __init__(self, snapshots: list | None):
        self.ids: set[str] = set()
        self.names: set[str] = set()
        self.native_checkbox_ids: set[str] = set()
        self.all_text: str = ""
        self.has_snapshots = bool(snapshots)

        if not snapshots:
            return

        text_parts = []
        for snap in snapshots:
            for inp in getattr(snap, "inputs", []):
                if inp.get("id"):
                    self.ids.add(inp["id"])
                    if inp.get("type") in ("checkbox", "radio"):
                        self.native_checkbox_ids.add(inp["id"])
                if inp.get("name"):
                    self.names.add(inp["name"])
                text_parts.append(inp.get("label", "") + " " + inp.get("placeholder", ""))
            for btn in getattr(snap, "buttons", []):
                sel = btn.get("selector", "")
                if sel.startswith("#"):
                    self.ids.add(sel[1:])
                m = re.match(r'\[name="(.+)"\]', sel)
                if m:
                    self.names.add(m.group(1))
                text_parts.append(btn.get("text", ""))
            for link in getattr(snap, "links", []):
                text_parts.append(link.get("text", "") + " " + (link.get("href") or ""))
            for dd in getattr(snap, "dropdowns", []):
                if dd.get("id"):
                    self.ids.add(dd["id"])
                if dd.get("name"):
                    self.names.add(dd["name"])
                for opt in dd.get("options", []):
                    text_parts.append(opt.get("text", ""))
            for form in getattr(snap, "forms", []):
                if form.get("id"):
                    self.ids.add(form["id"])
            for menu in getattr(snap, "menus", []):
                text_parts.append(menu.get("toggle", ""))
                for item in menu.get("items", []):
                    text_parts.append(item.get("text", "") + " " + (item.get("href") or ""))
            text_parts.append(getattr(snap, "aria", ""))
            text_parts.extend(getattr(snap, "headings", []))
            text_parts.append(getattr(snap, "visible_text", ""))

        self.all_text = " ".join(text_parts).lower()

    def has_text(self, needle: str) -> bool:
        return needle.lower() in self.all_text


# Strings that commonly appear in code but aren't DOM text to validate
_SKIP_TEXT_PREFIXES = ("/", "http", "#", ".", "input", "button", "select", "a[", "tr", "td", "div", "span")


def _extract_string_arg(call_src: str) -> str | None:
    """Pull the first string literal out of a call snippet."""
    m = re.search(r'''["']([^"']+)["']''', call_src)
    return m.group(1) if m else None


def lint_test_code(code: str, snapshots: list | None = None) -> list[LintIssue]:
    """Lint generated test code. Returns a list of issues (may be empty)."""
    issues: list[LintIssue] = []
    index = SnapshotIndex(snapshots)
    lines = code.split("\n")

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # --- Forbidden patterns (always wrong in this pipeline) ----------
        if "to_have_title(" in stripped:
            issues.append(LintIssue(lineno, "error",
                "to_have_title() breaks on site-name suffixes. Use "
                "expect(page.get_by_role('heading', name=...)).to_be_visible() instead."))

        m = re.search(r'to_have_url\(\s*["\'](/[^"\']*)["\']', stripped)
        if m:
            issues.append(LintIssue(lineno, "error",
                f"to_have_url('{m.group(1)}') compares against the FULL URL and will fail. "
                f"Use: assert \"{m.group(1)}\" in page.url"))

        m = re.search(r'to_have_count\(\s*(\d+)\s*\)', stripped)
        if m and int(m.group(1)) > 0:
            issues.append(LintIssue(lineno, "warning",
                f"to_have_count({m.group(1)}) with an exact count — pages usually have "
                f"pre-existing items. Use `assert locator.count() >= {m.group(1)}` unless "
                f"this exact count was verified in the DOM snapshot."))

        # --- Checkbox API on non-native elements --------------------------
        m = re.search(r'locator\(\s*["\']#([A-Za-z0-9_\-]+)["\']\s*\)[^#\n]*\.(check|uncheck|is_checked)\(', stripped)
        if m and index.has_snapshots:
            el_id = m.group(1)
            if el_id in index.ids and el_id not in index.native_checkbox_ids:
                issues.append(LintIssue(lineno, "error",
                    f".{m.group(2)}() on '#{el_id}' — the DOM snapshot shows this is NOT a "
                    f"native <input type='checkbox'>. Use .click() to toggle and class/aria "
                    f"attributes to read state."))

        # --- Selector whitelist against crawled DOM -----------------------
        if index.has_snapshots:
            # #id selectors
            for sel_m in re.finditer(r'''["']#([A-Za-z][A-Za-z0-9_\-]*)["']''', stripped):
                el_id = sel_m.group(1)
                if el_id not in index.ids and not index.has_text(el_id):
                    issues.append(LintIssue(lineno, "warning",
                        f"Selector '#{el_id}' was not seen in any crawled DOM snapshot — "
                        f"it may be hallucinated. Verify against the page context or replace "
                        f"with a selector that appears in the snapshots."))

            # [name=...] selectors
            for sel_m in re.finditer(r'''\[name=["\']?([A-Za-z0-9_\-$.]+)["\']?\]''', stripped):
                el_name = sel_m.group(1)
                if el_name not in index.names:
                    issues.append(LintIssue(lineno, "warning",
                        f"Selector '[name={el_name}]' was not seen in any crawled DOM snapshot — "
                        f"it may be hallucinated."))

            # text= / get_by_text literals
            for txt_m in re.finditer(r'''text=["\']?([^"'\)\]]+)''', stripped):
                txt = txt_m.group(1).strip()
                if len(txt) >= 4 and not txt.startswith(_SKIP_TEXT_PREFIXES) and not index.has_text(txt):
                    issues.append(LintIssue(lineno, "warning",
                        f"Text '{txt}' was not seen in any crawled page — the locator may "
                        f"never match. Verify the exact wording against the DOM snapshots."))

            for call_m in re.finditer(r'get_by_text\(([^)]*)\)', stripped):
                txt = _extract_string_arg(call_m.group(1))
                if txt and len(txt) >= 4 and not index.has_text(txt):
                    issues.append(LintIssue(lineno, "warning",
                        f"get_by_text('{txt}') — this text was not seen in any crawled page. "
                        f"Verify the exact wording against the DOM snapshots."))

    # Deduplicate identical messages on the same line
    seen = set()
    unique: list[LintIssue] = []
    for issue in issues:
        key = (issue.line, issue.message)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def format_issues(issues: list[LintIssue]) -> str:
    """Format issues as a text block for logging or for the AI fix prompt."""
    return "\n".join(str(i) for i in issues)
