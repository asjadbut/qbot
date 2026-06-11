"""
Page crawler: opens the target app in Chrome, waits for user to log in,
crawls relevant pages, captures simplified DOM snapshots, and saves the
authenticated browser state for reuse by the test runner.
"""

import os
import re
import json
import time
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Page

from qbot.config import config
from qbot.test_runner import find_chrome

LOGIN_PATTERNS = ["/login", "/signin", "/auth", "/account/login", "/sso"]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
window.chrome = { runtime: {} };
"""


@dataclass
class PageSnapshot:
    url: str
    title: str
    requested_url: str = ""  # original URL before any redirect
    headings: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)      # [{text, href}]
    buttons: list[dict] = field(default_factory=list)     # [{text, selector}]
    inputs: list[dict] = field(default_factory=list)      # [{name, type, id, placeholder, selector}]
    forms: list[dict] = field(default_factory=list)       # [{action, method, id}]
    dropdowns: list[dict] = field(default_factory=list)   # [{id, name, options:[]}]
    menus: list[dict] = field(default_factory=list)       # [{toggle, items:[{text, selector}]}] — revealed by clicking dropdown toggles
    aria: str = ""                                         # accessibility tree snapshot (roles + names)
    visible_text: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "headings": self.headings,
            "links": self.links[:30],
            "buttons": self.buttons[:30],
            "inputs": self.inputs[:30],
            "forms": self.forms[:10],
            "dropdowns": self.dropdowns[:15],
            "menus": self.menus[:10],
            "visible_text_snippet": self.visible_text[:2000],
        }

    def to_cache_dict(self) -> dict:
        """Full serialization for the crawl cache (lossless)."""
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_cache_dict(cls, d: dict) -> "PageSnapshot":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


def _clean_url(url: str) -> str:
    """Strip trailing junk chars like |, ], ), etc. from extracted URLs."""
    url = url.rstrip('.,;)]}|"\'')
    # Remove pipe and everything after it (malformed wiki/markdown links)
    if "|" in url:
        url = url.split("|")[0]
    # Remove trailing brackets
    url = url.rstrip("]}")
    return url


def extract_urls_from_text(text: str, base_url: str) -> list[str]:
    """Extract page paths/URLs from ticket text that belong to the target app."""
    urls = set()
    base = base_url.rstrip("/")
    base_host = re.sub(r'https?://', '', base).split('/')[0]  # e.g. my-dev.paradym.com

    # Build a set of host variants to recognise (e.g. my.paradym.com, my-dev.paradym.com)
    # Strip common env prefixes to get the core domain for fuzzy matching
    _ENV_PREFIX = r'^(my-dev|my-qa|my-staging|my-uat|staging|www|app|dev|qa|uat|test|my)[-.]?'
    _core = re.sub(_ENV_PREFIX, '', base_host)
    def _is_same_app(hostname: str) -> bool:
        """Check if a hostname is a variant of the target app."""
        h = hostname.lower()
        if h == base_host:
            return True
        h_core = re.sub(_ENV_PREFIX, '', h)
        return h_core == _core and len(_core) > 3

    # Find explicit URLs — rewrite to target host if it's a variant
    for match in re.finditer(r'https?://([^/\s<>"\']+)(/[^\s<>"\']*)?', text):
        hostname = match.group(1)
        path = match.group(2) or "/"
        path = _clean_url(path)
        if _is_same_app(hostname):
            urls.add(base + path)

    # Find relative paths like /Management/Dashboard or /maint/something.aspx
    for match in re.finditer(r'(/[A-Za-z][A-Za-z0-9_/.-]+(?:\?[^\s<>"\']*)?)' , text):
        path = _clean_url(match.group(1))
        if len(path) > 3 and not path.startswith("//"):
            # Skip paths that look like they contain a hostname
            first_segment = path.split('/')[1] if '/' in path[1:] else path[1:]
            if '.' in first_segment and len(first_segment) > 5:
                continue  # e.g. /my.paradym.com/... — skip, already handled above
            urls.add(base + path)

    return list(urls)


def _capture_snapshot(page: Page) -> PageSnapshot:
    """Capture a simplified DOM snapshot of the current page."""
    snapshot = PageSnapshot(
        url=page.url,
        title=page.title(),
    )

    # Headings
    snapshot.headings = page.eval_on_selector_all(
        "h1, h2, h3",
        "els => els.map(e => e.textContent.trim()).filter(t => t.length > 0)"
    )

    # Links
    snapshot.links = page.eval_on_selector_all(
        "a[href]",
        """els => els.slice(0, 40).map(e => ({
            text: e.textContent.trim().substring(0, 80),
            href: e.getAttribute('href')
        })).filter(l => l.text.length > 0)"""
    )

    # Buttons
    snapshot.buttons = page.eval_on_selector_all(
        "button, input[type='submit'], input[type='button'], a.btn, [role='button']",
        """els => els.slice(0, 40).map(e => {
            let text = e.textContent?.trim() || e.value || e.getAttribute('aria-label') || '';
            let sel = '';
            if (e.id) sel = '#' + e.id;
            else if (e.getAttribute('data-testid')) sel = '[data-testid=\"' + e.getAttribute('data-testid') + '\"]';
            else if (e.name) sel = '[name=\"' + e.name + '\"]';
            else if (text) sel = 'text=' + text.substring(0, 40);
            return {text: text.substring(0, 60), selector: sel};
        }).filter(b => b.text.length > 0)"""
    )

    # Inputs
    snapshot.inputs = page.eval_on_selector_all(
        "input, textarea, select",
        """els => els.slice(0, 50).map(e => {
            let sel = '';
            if (e.id) sel = '#' + e.id;
            else if (e.getAttribute('data-testid')) sel = '[data-testid=\"' + e.getAttribute('data-testid') + '\"]';
            else if (e.name) sel = '[name=\"' + e.name + '\"]';
            else sel = e.tagName.toLowerCase() + '[type=\"' + (e.type || 'text') + '\"]';
            return {
                name: e.name || '',
                type: e.type || e.tagName.toLowerCase(),
                id: e.id || '',
                placeholder: e.placeholder || '',
                selector: sel,
                label: (e.labels && e.labels[0]) ? e.labels[0].textContent.trim() : ''
            };
        })"""
    )

    # Forms
    snapshot.forms = page.eval_on_selector_all(
        "form",
        """els => els.slice(0, 10).map(e => ({
            action: e.action || '',
            method: e.method || 'get',
            id: e.id || ''
        }))"""
    )

    # Dropdowns (select elements with options)
    snapshot.dropdowns = page.eval_on_selector_all(
        "select",
        """els => els.slice(0, 15).map(e => ({
            id: e.id || '',
            name: e.name || '',
            options: Array.from(e.options).slice(0, 20).map(o => ({
                value: o.value, text: o.textContent.trim()
            }))
        }))"""
    )

    # Visible text (trimmed)
    snapshot.visible_text = page.eval_on_selector(
        "body",
        "el => el.innerText.substring(0, 2000)"
    )

    # ARIA accessibility snapshot — compact role/name tree, very LLM-friendly
    # (Playwright >= 1.49; degrade silently on older versions)
    try:
        snapshot.aria = page.locator("body").aria_snapshot()[:3500]
    except Exception:
        snapshot.aria = ""

    # Expand dropdown menus — reveals items that are invisible until the
    # toggle is clicked, so the AI knows the correct interaction pattern
    snapshot.menus = _expand_dropdown_menus(page)

    return snapshot


_DROPDOWN_TOGGLE_SELECTOR = (
    ".dropdown-toggle, [data-toggle='dropdown'], [data-bs-toggle='dropdown'], "
    "button[aria-haspopup='true'], button[aria-haspopup='menu']"
)


def _expand_dropdown_menus(page: Page, max_menus: int = 5) -> list[dict]:
    """Click visible dropdown toggles one at a time and capture the menu items
    they reveal. Closes each menu (Escape) before moving on. Best-effort —
    any failure just skips that toggle."""
    menus: list[dict] = []
    try:
        toggles = page.locator(_DROPDOWN_TOGGLE_SELECTOR)
        count = min(toggles.count(), 10)
    except Exception:
        return menus

    for i in range(count):
        if len(menus) >= max_menus:
            break
        toggle = toggles.nth(i)
        try:
            if not toggle.is_visible():
                continue
            label = (toggle.text_content() or toggle.get_attribute("aria-label") or "").strip()[:60]

            before = page.eval_on_selector_all(
                "a, button, [role='menuitem']",
                "els => els.filter(e => e.offsetParent !== null).length")
            toggle.click(timeout=2000)
            page.wait_for_timeout(400)

            # Items that became visible after the click
            items = page.eval_on_selector_all(
                ".dropdown-menu a, .dropdown-menu button, [role='menu'] [role='menuitem'], .dropdown-menu [role='menuitem']",
                """els => els.filter(e => e.offsetParent !== null).slice(0, 15).map(e => ({
                    text: (e.textContent || '').trim().substring(0, 60),
                    href: e.getAttribute('href') || ''
                })).filter(x => x.text.length > 0)"""
            )
            after = page.eval_on_selector_all(
                "a, button, [role='menuitem']",
                "els => els.filter(e => e.offsetParent !== null).length")

            if items and after > before:
                menus.append({"toggle": label or f"dropdown #{i + 1}", "items": items})

            # Close the menu before the next toggle
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            continue

    return menus


class PageCrawler:
    """Crawl target pages and capture DOM snapshots for AI context."""

    def __init__(self, on_log=None):
        self.on_log = on_log or (lambda msg: None)
        self.state_path = os.path.join(config.test_output_dir, "auth_state.json")
        self.snapshots: list[PageSnapshot] = []

    def crawl(self, ticket_text: str) -> list[PageSnapshot]:
        """
        Open Chrome, wait for login, crawl target pages, save auth state.
        Returns list of PageSnapshot objects.
        """
        base_url = config.target_base_url or "http://localhost:3000"
        chrome_path = find_chrome()

        # Extract URLs to visit from ticket text
        urls_to_visit = extract_urls_from_text(ticket_text, base_url)
        # Always include the base URL dashboard-level page
        if base_url not in urls_to_visit:
            urls_to_visit.insert(0, base_url)

        self.on_log(f"Found {len(urls_to_visit)} URLs to crawl from ticket")
        for u in urls_to_visit:
            self.on_log(f"   {u}")

        # Launch browser
        pw = sync_playwright().start()
        launch_args = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--disable-infobars",
                "--disable-extensions",
                "--window-size=1280,720",
            ],
        }
        if chrome_path:
            launch_args["executable_path"] = chrome_path

        browser = pw.chromium.launch(**launch_args)
        context = browser.new_context(
            base_url=base_url,
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()
        page.add_init_script(STEALTH_SCRIPT)

        # Navigate and handle login
        self.on_log(f"Opening {base_url}...")
        page.goto(base_url, wait_until="networkidle", timeout=60000)
        time.sleep(2)

        url_lower = page.url.lower()
        if any(p in url_lower for p in LOGIN_PATTERNS):
            self.on_log("Login page detected - please log in...")
            self.on_log(f"   URL: {page.url}")
            self.on_log("   Waiting up to 5 minutes...")
            page.wait_for_url(
                lambda u: not any(p in u.lower() for p in LOGIN_PATTERNS),
                timeout=300000,
            )
            self.on_log("Login successful!")
            time.sleep(2)

        # Now crawl each URL
        self.snapshots = []
        seen_urls = set()
        for url in urls_to_visit:
            try:
                self.on_log(f"Crawling: {url}")
                page.goto(url, wait_until="load", timeout=30000)
                time.sleep(2)  # let JS settle

                # Skip if redirected to login (session expired somehow)
                if any(p in page.url.lower() for p in LOGIN_PATTERNS):
                    self.on_log(f"   Skipped (redirected to login)")
                    continue

                # Skip if we already captured the final URL (redirect dedup)
                final_url = page.url.split('?')[0].rstrip('/')
                if final_url in seen_urls:
                    self.on_log(f"   Skipped (already captured via redirect to {page.url})")
                    continue
                seen_urls.add(final_url)

                snapshot = _capture_snapshot(page)
                # Track if this page was a redirect
                if page.url.rstrip('/') != url.rstrip('/'):
                    snapshot.requested_url = url
                    self.on_log(f"   Note: {url} redirected to {page.url}")
                self.snapshots.append(snapshot)
                self.on_log(f"   Captured: {snapshot.title} ({len(snapshot.buttons)} buttons, {len(snapshot.inputs)} inputs)")
            except Exception as e:
                self.on_log(f"   Error crawling {url}: {e}")

        # Save auth state for test runner reuse
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        context.storage_state(path=self.state_path)
        self.on_log(f"Auth state saved: {self.state_path}")

        page.close()
        context.close()
        browser.close()
        pw.stop()

        return self.snapshots

    def get_snapshots_text(self) -> str:
        """Format captured snapshots as text for the AI prompt."""
        if not self.snapshots:
            return ""

        sections = []
        for snap in self.snapshots:
            parts = [f"## Page: {snap.url}", f"Title: {snap.title}"]

            if snap.requested_url:
                parts.insert(1, f"NOTE: Requested URL {snap.requested_url} REDIRECTED to {snap.url}")

            if snap.headings:
                parts.append(f"Headings: {', '.join(snap.headings[:10])}")

            if snap.buttons:
                btn_lines = [f"  - \"{b['text']}\" → {b['selector']}" for b in snap.buttons[:20]]
                parts.append("Buttons/Actions:\n" + "\n".join(btn_lines))

            if snap.inputs:
                inp_lines = []
                for inp in snap.inputs[:20]:
                    label = inp.get("label") or inp.get("placeholder") or inp.get("name") or inp.get("id") or "unnamed"
                    inp_lines.append(f"  - {label} ({inp['type']}) → {inp['selector']}")
                parts.append("Inputs/Fields:\n" + "\n".join(inp_lines))

            if snap.links:
                link_lines = [f"  - \"{l['text']}\" → {l['href']}" for l in snap.links[:20]]
                parts.append("Links:\n" + "\n".join(link_lines))

            if snap.dropdowns:
                for dd in snap.dropdowns[:10]:
                    opts = [f"{o['text']}" for o in dd.get("options", [])[:10]]
                    parts.append(f"Dropdown ({dd['name'] or dd['id']}): [{', '.join(opts)}]")

            if snap.menus:
                for menu in snap.menus[:8]:
                    item_lines = [
                        f"    - \"{it['text']}\"" + (f" → {it['href']}" if it.get("href") and it["href"] != "#" else "")
                        for it in menu.get("items", [])[:12]
                    ]
                    parts.append(
                        f"Dropdown menu \"{menu['toggle']}\" (items hidden until the toggle button is CLICKED):\n"
                        + "\n".join(item_lines)
                    )

            if snap.forms:
                form_lines = [f"  - action={f['action']} method={f['method']}" for f in snap.forms]
                parts.append("Forms:\n" + "\n".join(form_lines))

            if snap.aria:
                parts.append(f"Accessibility tree (role/name — prefer get_by_role() locators from this):\n{snap.aria}")

            if snap.visible_text:
                parts.append(f"Visible text (excerpt):\n{snap.visible_text[:1500]}")

            sections.append("\n".join(parts))

        return "\n\n---\n\n".join(sections)
