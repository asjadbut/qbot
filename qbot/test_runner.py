import os
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

    def run_tests(self, filepath: str = None) -> TestResult:
        """Execute tests using pytest and return results."""
        cmd = [
            "python", "-m", "pytest",
            filepath or self.test_dir,
            "-v",
            "--tb=short",
            "--no-header",
            "-p", "no:playwright",  # disable pytest-playwright — we manage the browser ourselves
        ]

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

        for line in output.split("\n"):
            line_stripped = line.strip()

            # Parse individual test results (verbose mode: "path::Class::test PASSED")
            if "::" in line_stripped:
                if " PASSED" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    individual.append({"name": name, "status": "PASSED", "message": ""})
                elif " FAILED" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    individual.append({"name": name, "status": "FAILED", "message": line_stripped})
                elif " ERROR" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    individual.append({"name": name, "status": "ERROR", "message": line_stripped})
                elif " SKIPPED" in line_stripped:
                    name = self._extract_test_name(line_stripped)
                    individual.append({"name": name, "status": "SKIPPED", "message": ""})

            # Parse summary line: "= 5 failed, 1 passed in 101.31s ="
            # Only match the final summary (line made of = signs with counts)
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

    def cleanup(self):
        """Remove generated test files."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
