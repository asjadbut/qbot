import os
import sys
import subprocess
import shutil
from dataclasses import dataclass
from qbot.config import config

# Common Chrome installation paths on Windows
_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str | None:
    """Return the path to Google Chrome if installed, else None."""
    for path in _CHROME_PATHS:
        if os.path.isfile(path):
            return path
    return None


@dataclass
class TestResult:
    passed: int
    failed: int
    errors: int
    skipped: int
    total: int
    output: str
    success: bool
    individual_results: list  # list of dicts with test name, status, message


class TestRunner:
    def __init__(self):
        self.test_dir = config.test_output_dir
        os.makedirs(self.test_dir, exist_ok=True)
        self.chrome_path: str | None = None  # set after first conftest write
        self._reruns_available: bool | None = None  # lazily probed

    @staticmethod
    def _strip_fixture_redefinitions(code: str) -> str:
        """Use AST to remove @pytest.fixture defs that would override conftest fixtures.
        Works reliably regardless of blank lines, multi-line bodies, or decorator args.
        """
        import ast as _ast
        PROTECTED = {
            "page", "browser", "authed_context",
            "browser_context", "browser_context_args", "browser_type_launch_args",
        }

        try:
            tree = _ast.parse(code)
        except SyntaxError:
            return code  # unparseable — return unchanged

        lines_to_remove: set[int] = set()
        for node in tree.body:  # top-level only — don't touch class methods
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            if node.name not in PROTECTED:
                continue
            # Check at least one decorator is pytest.fixture (or pytest.fixture(...))
            for deco in node.decorator_list:
                is_fixture = (
                    (isinstance(deco, _ast.Name) and deco.id == "fixture")
                    or (isinstance(deco, _ast.Attribute) and deco.attr == "fixture")
                    or (
                        isinstance(deco, _ast.Call)
                        and (
                            (isinstance(deco.func, _ast.Name) and deco.func.id == "fixture")
                            or (isinstance(deco.func, _ast.Attribute) and deco.func.attr == "fixture")
                        )
                    )
                )
                if is_fixture:
                    start = min(d.lineno for d in node.decorator_list)
                    for ln in range(start, node.end_lineno + 1):
                        lines_to_remove.add(ln)
                    break

        if not lines_to_remove:
            return code

        result = []
        for i, line in enumerate(code.splitlines(keepends=True), start=1):
            if i not in lines_to_remove:
                result.append(line)
        return "".join(result)

    def _clean_old_tests(self):
        """Remove all test_*.py files from previous runs."""
        import glob
        for f in glob.glob(os.path.join(self.test_dir, "test_*.py")):
            os.remove(f)

    def write_test_file(self, code: str, filename: str = "test_generated.py") -> str:
        """Write generated test code to a file."""
        filepath = os.path.join(self.test_dir, filename)
        # Clean stale test files from previous runs
        self._clean_old_tests()
        # Always (re)write conftest so Chrome path and base URL are current
        self.chrome_path = self._ensure_conftest()
        code = self._strip_fixture_redefinitions(code)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return filepath

    def append_tests(self, code: str, filename: str = "test_generated_round2.py") -> str:
        """Write additional tests to a separate file."""
        filepath = os.path.join(self.test_dir, filename)
        code = self._strip_fixture_redefinitions(code)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return filepath

    @staticmethod
    def _python_command() -> str:
        """Resolve the Python interpreter to run pytest with.

        sys.executable is correct when running from source. In a PyInstaller
        frozen exe, sys.executable is QBot.exe — fall back to python on PATH.
        """
        if getattr(sys, "frozen", False):
            return shutil.which("python") or shutil.which("py") or "python"
        return sys.executable

    def _supports_reruns(self) -> bool:
        """Check (once) whether pytest-rerunfailures is installed in the
        interpreter that will run the tests."""
        if self._reruns_available is None:
            try:
                probe = subprocess.run(
                    [self._python_command(), "-c", "import pytest_rerunfailures"],
                    capture_output=True, timeout=20,
                )
                self._reruns_available = probe.returncode == 0
            except Exception:
                self._reruns_available = False
        return self._reruns_available

    def run_tests(self, filepath: str = None) -> TestResult:
        """Execute tests using pytest and return results."""
        junit_path = os.path.join(self.test_dir, ".qbot_results.xml")
        if os.path.exists(junit_path):
            try:
                os.remove(junit_path)
            except OSError:
                pass

        cmd = [
            self._python_command(), "-m", "pytest",
            filepath or self.test_dir,
            "-v",
            "--tb=short",
            "--no-header",
            f"--junitxml={junit_path}",
            "-p", "no:playwright",  # disable pytest-playwright — we manage the browser ourselves
        ]
        # Retry failures once — separates flaky timing failures from real bugs,
        # so the AI repair loop only sees genuine failures.
        if self._supports_reruns():
            cmd += ["--reruns", "1", "--reruns-delay", "2"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=self.test_dir,
                env={**os.environ, "PYTHONPATH": self.test_dir},
            )
            output = result.stdout + "\n" + result.stderr
            # Prefer structured JUnit XML results; fall back to regex parsing
            parsed = self._parse_junit_xml(junit_path, output)
            if parsed is not None:
                return parsed
            return self._parse_results(output)
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=0, failed=0, errors=0, skipped=0, total=0,
                output="Test execution timed out after 10 minutes",
                success=False, individual_results=[],
            )
        except Exception as e:
            return TestResult(
                passed=0, failed=0, errors=0, skipped=0, total=0,
                output=f"Test execution error: {str(e)}",
                success=False, individual_results=[],
            )

    def run_all_tests(self) -> TestResult:
        """Run all test files in the test directory."""
        return self.run_tests(self.test_dir)

    def _parse_junit_xml(self, xml_path: str, output: str) -> TestResult | None:
        """Parse pytest's JUnit XML report — structured and reliable.

        Returns None if the XML is missing/unreadable so the caller can fall
        back to regex parsing of the console output.
        """
        import xml.etree.ElementTree as ET

        if not os.path.isfile(xml_path):
            return None
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError:
            return None

        passed = failed = errors = skipped = 0
        individual = []

        for case in root.iter("testcase"):
            name = case.get("name", "unknown")
            failure = case.find("failure")
            error = case.find("error")
            skip = case.find("skipped")

            if failure is not None:
                failed += 1
                raw = (failure.get("message") or "") + "\n" + (failure.text or "")
                individual.append({
                    "name": name, "status": "FAILED",
                    "message": self._humanize_failure(raw),
                    "detail": raw.strip(),
                })
            elif error is not None:
                errors += 1
                raw = (error.get("message") or "") + "\n" + (error.text or "")
                individual.append({
                    "name": name, "status": "ERROR",
                    "message": self._humanize_failure(raw),
                    "detail": raw.strip(),
                })
            elif skip is not None:
                skipped += 1
                individual.append({
                    "name": name, "status": "SKIPPED",
                    "message": skip.get("message", ""), "detail": "",
                })
            else:
                passed += 1
                individual.append({"name": name, "status": "PASSED", "message": "", "detail": ""})

        total = passed + failed + errors + skipped
        if total == 0:
            return None  # collection error etc. — let regex parser surface it

        return TestResult(
            passed=passed, failed=failed, errors=errors, skipped=skipped,
            total=total, output=output,
            success=(failed == 0 and errors == 0 and total > 0),
            individual_results=individual,
        )

    def _ensure_conftest(self):
        """Create conftest.py that manages ONE browser, ONE context, shared across all tests."""
        conftest_path = os.path.join(self.test_dir, "conftest.py")
        chrome_path = find_chrome()
        base_url = config.target_base_url or "http://localhost:3000"
        auth_state = os.path.join(self.test_dir, "auth_state.json")
        has_state = os.path.isfile(auth_state)

        if chrome_path:
            chrome_line = f'        executable_path=r"{chrome_path}",'
            chrome_note = f"# Using Google Chrome: {chrome_path}"
        else:
            chrome_line = "        # executable_path not set — using bundled Chromium"
            chrome_note = "# WARNING: Google Chrome not found; falling back to Playwright's bundled Chromium."

        # If we have saved auth state from the crawl step, load it directly
        if has_state:
            state_line = f'        storage_state=r"{auth_state}",'
        else:
            state_line = "        # No saved auth state — will need manual login"

        conftest_code = f'''import pytest
import os
from playwright.sync_api import sync_playwright, expect

{chrome_note}

BASE_URL = "{base_url}"
AUTH_STATE = r"{auth_state}"
LOGIN_PATTERNS = ["/login", "/signin", "/auth", "/account/login", "/sso"]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
Object.defineProperty(navigator, 'languages', {{get: () => ['en-US', 'en']}});
Object.defineProperty(navigator, 'plugins', {{get: () => [1, 2, 3]}});
window.chrome = {{ runtime: {{}} }};
"""


@pytest.fixture(scope="session")
def _pw_session():
    """Launch exactly ONE browser for the entire test session."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
{chrome_line}
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-popup-blocking",
            "--ignore-certificate-errors",
            "--window-size=1280,720",
        ],
    )

    # Load saved auth state if available (from crawl step)
    ctx_args = dict(
        base_url=BASE_URL,
        viewport={{"width": 1280, "height": 720}},
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    if os.path.isfile(AUTH_STATE):
        ctx_args["storage_state"] = AUTH_STATE

    context = browser.new_context(**ctx_args)

    # Verify auth is still valid
    check_page = context.new_page()
    check_page.add_init_script(STEALTH_SCRIPT)
    check_page.goto(BASE_URL, wait_until="load", timeout=60000)

    import time
    time.sleep(2)
    url = check_page.url.lower()
    if any(p in url for p in LOGIN_PATTERNS):
        print()
        print("=" * 60)
        print("  AUTHENTICATION REQUIRED")
        print(f"  Please log in at: {{check_page.url}}")
        print("  Waiting up to 5 minutes...")
        print("=" * 60)
        print()
        check_page.wait_for_url(
            lambda u: not any(p in u.lower() for p in LOGIN_PATTERNS),
            timeout=300000,
        )
        print("  Login detected - starting tests...")
        print()

    check_page.close()

    yield context

    context.close()
    browser.close()
    pw.stop()


@pytest.fixture
def page(_pw_session):
    """Each test gets a fresh tab in the shared authenticated context."""
    p = _pw_session.new_page()
    p.add_init_script(STEALTH_SCRIPT)
    yield p
    p.close()
'''
        with open(conftest_path, "w", encoding="utf-8") as f:
            f.write(conftest_code)

        return chrome_path  # caller can warn user if None

    @staticmethod
    def _extract_test_name(line: str) -> str:
        """Get the last :: segment (actual test function name) from a pytest line."""
        # e.g. "test_generated.py::TestClass::test_method PASSED"
        parts = line.split("::")
        # last part may have " PASSED" etc. appended
        return parts[-1].split()[0] if parts else line

    def _parse_results(self, output: str) -> TestResult:
        """Parse pytest output to extract test results."""
        import re
        passed = failed = errors = skipped = 0
        individual = []

        # Extract failure details from pytest sections like "_ TestClass.test_name _"
        failure_details = self._extract_failure_details(output)

        for line in output.split("\n"):
            line_stripped = line.strip()

            # Parse individual test results (verbose mode: "path::Class::test PASSED")
            if "::" in line_stripped:
                if " PASSED" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    individual.append({"name": name, "status": "PASSED", "message": ""})
                elif " FAILED" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    raw_detail = failure_details.get(name, line_stripped)
                    reason = self._humanize_failure(raw_detail)
                    individual.append({"name": name, "status": "FAILED", "message": reason})
                elif " ERROR" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    raw_detail = failure_details.get(name, line_stripped)
                    reason = self._humanize_failure(raw_detail)
                    individual.append({"name": name, "status": "ERROR", "message": reason})
                elif " SKIPPED" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    individual.append({"name": name, "status": "SKIPPED", "message": ""})

            # Parse summary line: "= 5 failed, 1 passed in 101.31s ="
            m = re.match(r'^=+\s(.+?)\s=+$', line_stripped)
            if m:
                summary_text = m.group(1)
                for token in re.findall(r'(\d+)\s+(passed|failed|error|skipped|warnings?)', summary_text):
                    count = int(token[0])
                    kind = token[1]
                    if kind == "passed":
                        passed = count
                    elif kind == "failed":
                        failed = count
                    elif kind == "error":
                        errors = count
                    elif kind == "skipped":
                        skipped = count

        total = passed + failed + errors + skipped

        # Deduplicate individual results (verbose line + summary line can both match)
        seen = set()
        unique = []
        for item in individual:
            key = (item["name"], item["status"])
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            total=total,
            output=output,
            success=(failed == 0 and errors == 0 and total > 0),
            individual_results=unique,
        )

    @staticmethod
    def _extract_failure_details(output: str) -> dict[str, str]:
        """Extract the failure block for each test from pytest output.

        Pytest formats failures as:
            _ TestClass.test_name _
            ...error lines...
            _ NextTest _   (or === summary ===)

        Returns {test_name: raw_error_text}.
        """
        import re
        details: dict[str, str] = {}
        lines = output.split("\n")
        i = 0
        while i < len(lines):
            # Match section headers: "_ TestClass.test_name _" or "_ test_name _"
            m = re.match(r'^_+\s+(.+?)\s+_+$', lines[i].strip())
            if m:
                section_name = m.group(1)
                # Extract the test function name (last segment after .)
                test_name = section_name.split(".")[-1].strip()
                # Collect lines until next section or summary
                block_lines = []
                i += 1
                while i < len(lines):
                    l = lines[i].strip()
                    if re.match(r'^_+\s+.+\s+_+$', l) or re.match(r'^=+\s', l):
                        break
                    block_lines.append(lines[i])
                    i += 1
                details[test_name] = "\n".join(block_lines)
            else:
                i += 1
        return details

    @staticmethod
    def _humanize_failure(raw: str) -> str:
        """Convert raw pytest error output into a concise human-readable explanation."""
        import re

        # TimeoutError — element not found or not visible
        m = re.search(r'TimeoutError.*?Timeout (\d+)ms exceeded', raw)
        if m:
            timeout_s = int(m.group(1)) // 1000
            # What was it waiting for?
            loc = re.search(r'waiting for locator\("([^"]+)"\)', raw)
            locator_desc = loc.group(1) if loc else "an element"
            # Why?
            if "element is not visible" in raw:
                return f"Timed out after {timeout_s}s — the element \"{locator_desc}\" exists in the page but is not visible (likely hidden in a menu or collapsed section)."
            if "element is not stable" in raw:
                return f"Timed out after {timeout_s}s — the element \"{locator_desc}\" was found but kept moving or resizing."
            return f"Timed out after {timeout_s}s waiting for \"{locator_desc}\" to appear on the page."

        # Element not visible (non-timeout)
        if "Element is not visible" in raw:
            loc = re.search(r'waiting for locator\("([^"]+)"\)', raw)
            locator_desc = loc.group(1) if loc else "an element"
            return f"The element \"{locator_desc}\" exists but is not visible — it may be hidden inside a dropdown or collapsed menu."

        # AssertionError with "to_be_visible" / expected to be visible
        if "expected to be visible" in raw.lower():
            loc = re.search(r'waiting for locator\("([^"]+)"\)', raw)
            locator_desc = loc.group(1) if loc else "an element"
            return f"Expected \"{locator_desc}\" to be visible, but it was hidden."

        # AssertionError — URL assertion
        m = re.search(r"assert ['\"](.+?)['\"] (?:not )?in ['\"](.+?)['\"]", raw)
        if m:
            expected = m.group(1)
            actual = m.group(2)
            if "not in" in raw[raw.find("assert"):raw.find("assert")+100]:
                return f"Expected the URL to NOT contain \"{expected}\", but the page stayed at \"{actual}\"."
            return f"Expected the URL to contain \"{expected}\", but the page was at \"{actual}\"."

        # AssertionError — URL with 'is contained here'
        m = re.search(r"'(.+?)' is contained here:\s*\n\s*(\S+)", raw)
        if m:
            return f"Expected the URL to NOT contain \"{m.group(1)}\", but the page was at \"{m.group(2)}\"."

        # AssertionError — count mismatch
        m = re.search(r'expected to have count (\d+)', raw)
        if m:
            expected = m.group(1)
            loc = re.search(r'waiting for locator\("([^"]+)"\)', raw)
            locator_desc = loc.group(1) if loc else "elements"
            actual_m = re.search(r'Actual value:\s*(\d+)', raw)
            actual = actual_m.group(1) if actual_m else "a different number"
            return f"Expected {expected} \"{locator_desc}\" element(s), but found {actual}."

        # AssertionError — generic
        m = re.search(r'AssertionError:\s*(.+)', raw)
        if not m:
            m = re.search(r'AssertionError:\s*(.+)', raw)
        if m:
            return f"Assertion failed: {m.group(1).strip()}"

        # Error line (E   ...)
        e_lines = re.findall(r'^E\s+(.+)$', raw, re.MULTILINE)
        if e_lines:
            # Take the most descriptive E line (skip "Call log:" etc.)
            for eline in e_lines:
                eline = eline.strip()
                if eline.startswith("Call log"):
                    continue
                if eline.startswith("-"):
                    continue
                if len(eline) > 10:
                    return eline
            return e_lines[0].strip()

        # Fallback — first non-empty line
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("E ") and len(line) > 5:
                return line[:200]

        return "Test failed (see raw output for details)."

    def cleanup(self):
        """Remove generated test files."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
