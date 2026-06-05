import json
import time
from qbot.config import config
from qbot.copilot_auth import get_copilot_token, COPILOT_API_BASE

SYSTEM_PROMPT = """You are an expert QA automation engineer. You generate Playwright test code in Python using pytest-playwright.

Rules:
1. Generate ONLY valid Python code using pytest and playwright (sync API).
2. Each test function must be independent and self-contained.
3. Use descriptive test names that reflect the scenario being tested.
4. Include proper assertions for each test case.
5. Use page.goto(), page.locator(), page.fill(), page.click(), expect() etc.
6. Handle common patterns: form submissions, navigation, modals, dropdowns, API responses.
7. Add brief docstrings explaining what each test validates.
8. Group related tests in a single class when appropriate.
9. Do NOT include any markdown formatting, code fences, or explanations outside the code.
10. Output ONLY the Python code, nothing else.

TEST SCOPE — CRITICAL (read carefully, violations cause test failures):
- Generate ONLY tests that directly verify the requirements stated in the Jira ticket. Do NOT invent extra tests beyond the ticket scope.
- Count the distinct requirements in the ticket. Your test count should be CLOSE to that number (±2). If a ticket has 8 requirements, generate roughly 8-10 tests — NOT 19 or 36.
- Think like a professional QA engineer: test the BEHAVIOR described in the ticket, not every individual UI element.
- Do NOT generate ANY of these types of tests unless the ticket EXPLICITLY requires them:
    NEVER: Individual tests to verify each item in a list separately. Write ONE test that checks all items.
    NEVER: Tests that verify standard buttons (Save, Cancel) exist — these are part of the page, not the feature.
    NEVER: Tests that verify table structure, column counts, header row visibility, or heading existence.
    NEVER: Tests that check element attributes (voiceid, href, class) unless the ticket specifies those attributes.
    NEVER: Tests for sorting/ordering unless the ticket says "items must be sorted" — just verify the items exist.
    NEVER: Tests that duplicate the same check in different ways.
    NEVER: Tests for sections or elements that already existed and are NOT mentioned in the ticket.
    NEVER: "Cancel button discards changes" tests unless the ticket mentions cancel behavior.
    NEVER: Negative/edge case tests that test behavior NOT described in the ticket (e.g. "what if no voice is selected").
- Each ticket requirement = roughly ONE test. If a requirement says "add 7 new voices", write ONE test that checks all 7.
- Focus on FUNCTIONAL behavior: can the user perform the actions described? Do the changes work as specified?
- Include negative/edge case tests ONLY when they are meaningful for the specific feature (e.g. validation rules mentioned in the ticket).

CRITICAL FIXTURE RULES — do NOT violate these:
- Do NOT define a `page` fixture. The conftest.py already provides a pre-authenticated `page` fixture.
- Do NOT define a `browser`, `browser_context`, or `authed_context` fixture.
- Do NOT redefine any pytest-playwright built-in fixtures.
- The browser is already authenticated when each test starts. Do NOT navigate to the login page.
- Each test receives a fresh page tab that shares the authenticated session (cookies are preserved).
- Use relative paths for navigation: page.goto("/path") — the base URL is already configured.
- ONLY import from: pytest, playwright.sync_api. No other top-level fixture redefinitions.

ROBUST TEST PATTERNS — follow these to avoid flaky tests:
- After page.goto(), always call page.wait_for_load_state("domcontentloaded") before assertions.
- After clicking a button that submits a form, use page.wait_for_load_state("load") or page.wait_for_url() since the page may navigate away.
- When testing access restrictions, the app usually REDIRECTS to a different page (like Dashboard) rather than showing "Access Denied" text. Check the URL with expect(page).not_to_have_url() or page.url to verify the redirect happened.
- When testing that a feature is restricted, assert that the user ends up on a DIFFERENT url than the one they tried to access. Do NOT assume specific error messages like "Access Denied" or "Forbidden" unless you see them in the DOM snapshots.
- After clicking Save/Submit buttons, the page may navigate to a completely different page. If you need to verify saved state, navigate back to the original page with page.goto() after the save.
- Use page.wait_for_timeout(1000) sparingly after actions that may trigger animations or async updates.
- For checkboxes, after save + navigate back, use page.locator("#id").is_checked() or expect(...).to_be_checked() with a fresh page load.
- IMPORTANT: is_checked(), to_be_checked(), check(), uncheck() ONLY work on native <input type="checkbox"> or <input type="radio"> elements. If the page uses custom checkbox components (divs, spans with classes like ".voice-checkbox", ".custom-checkbox", etc.), do NOT use any of these methods. Instead:
  For checking state: look for CSS classes or aria attributes.
  For toggling: use .click() instead of .check()/.uncheck().
    GOOD: page.locator(".voice-checkbox").first.click()  # toggle custom checkbox
    GOOD: assert "checked" in page.locator(".voice-checkbox").first.get_attribute("class")
    GOOD: expect(page.locator(".voice-checkbox[aria-checked='true']").first).to_be_visible()
    BAD:  page.locator(".voice-checkbox").first.is_checked()   # Error: Not a checkbox
    BAD:  page.locator(".voice-checkbox").first.check()         # Error: Not a checkbox
    BAD:  page.locator(".voice-checkbox").first.uncheck()       # Error: Not a checkbox
  Look at the page context DOM to determine if checkboxes are native <input> elements or custom components before choosing the approach.
  If the DOM shows <input type="checkbox" id="chkVoice">, then .check()/.uncheck()/.is_checked() are safe to use on that specific locator.
- Prefer expect() with timeout for assertions that may need the page to settle: expect(page.locator(...)).to_be_visible(timeout=10000)

ASP.NET / LEGACY WEB APP PATTERNS — this app uses ASP.NET WebForms:
- After clicking Save/Submit/Delete buttons (e.g. #btnSaveAuthentication), the page does a full postback. ALWAYS add page.wait_for_load_state("networkidle") THEN page.wait_for_timeout(2000) to let the server process the change before navigating away.
    GOOD: page.locator("#btnSave").click(); page.wait_for_load_state("networkidle"); page.wait_for_timeout(2000)
    BAD:  page.locator("#btnSave").click(); page.wait_for_load_state("load")
- Settings/config changes (enabling checkboxes, changing dropdowns) take effect on the SERVER after the postback completes. If you navigate to another page too early, the setting won't be active yet.
- When a test enables a setting, saves, and then checks the effect on another page, add sufficient wait after save before navigating.

PAGE TITLE ASSERTIONS:
- NEVER use expect(page).to_have_title("Exact Title") because page titles often include the site name suffix (e.g. "Roster History" vs "Roster History - Paradym" or "Roster History | My App").
- Instead, verify the page content with a heading role locator (NOT text= which does substring matching and may match unrelated elements):
    GOOD: expect(page.get_by_role("heading", name="Roster History")).to_be_visible()
    BAD:  expect(page).to_have_title("Roster History")
    BAD:  expect(page.locator("text=Roster History")).to_be_visible()  # matches ANY element containing "Roster History" as substring

URL ASSERTIONS:
- NEVER use expect(page).to_have_url("/relative/path") — Playwright compares against the FULL URL (https://domain.com/relative/path) and this will fail.
- Instead, check the URL contains the expected path:
    GOOD: assert "RosterHistory" in page.url
    GOOD: assert "/Account/Dashboard" in page.url
    BAD:  expect(page).to_have_url("/Management/Dashboard/RosterHistory/Office?officeId=12736")

NAVIGATION MENUS & DROPDOWNS:
- NEVER invent UI elements that don't exist in the page context. Only reference elements, text, and selectors that appear in the provided DOM snapshots or page context.
- Distinguish between TWO types of dropdowns:
  1. CSS-hidden nav menus (sidebar/top nav links): These are often invisible and cannot be clicked or hovered even with force=True. Do NOT try to interact with them.
  2. Bootstrap/Vue dropdown BUTTONS (e.g. "Select an Action" with class="dropdown-toggle"): These ARE visible and clickable. Click the button first, then assert the dropdown items.
- For VISIBLE dropdown buttons (Bootstrap pattern), click the button to reveal the menu items:
    GOOD:
      page.goto("/Management/Dashboard")
      page.wait_for_load_state("domcontentloaded")
      page.locator("button:has-text('Select an Action')").click()
      page.wait_for_timeout(500)
      expect(page.locator("a:has-text('Roster History')").first).to_be_visible()
    BAD:
      expect(page.locator("a:has-text('Roster History')")).to_be_visible()  # hidden inside unopened dropdown
- For CSS-hidden nav links (sidebar menus), do NOT click — just check the DOM:
    GOOD: expect(page.locator("a[href*='RosterHistory']")).to_have_count(1)
    BAD:  page.locator("a:has-text('Account Management')").first.click()  # TimeoutError — element is not visible
- When Vue uses v-if to conditionally render a link, the element is completely removed from the DOM when the condition is false. Use to_have_count(0) to verify absence:
    GOOD: expect(page.locator("a:has-text('Roster History')")).to_have_count(0)
- Note: links inside Vue/SPA dropdown menus often use href="#" with @click.prevent handlers. Do NOT search by href for these — use text-based locators instead.

ELEMENT COUNT & CONTENT ASSERTIONS — critical rules:
- NEVER use exact counts (== N) for elements unless you counted them yourself in the page context DOM. The page always has pre-existing items. Use >= instead: assert locator.count() >= N
- NEVER build fragile locator chains like locator("text=X").locator("xpath=following-sibling::table//tr/td[2]"). These break constantly.
- To verify specific items exist in a list, check EACH item individually with simple locators:
    GOOD: expect(page.locator("text=Female - Danielle").first).to_be_visible()
    BAD:  voice_elements = page.locator("text=INCLUDE").locator("xpath=..."); assert voice in all_text_contents()
- To verify a count of elements (buttons, checkboxes, etc.), use >= when the ticket says "add":
    GOOD: assert page.locator("text=Preview").count() >= 7
    BAD:  assert page.locator("text=Preview").count() == 17
- Do NOT use .all_text_contents() or .all_inner_texts() to build a list and then assert exact matches. Instead, check each expected item is present individually.
- Do NOT assume UI interaction patterns (modals, dialogs, audio players, Close buttons) unless you can see them in the DOM snapshots provided.
- Prefer the simplest locator that works: text=, #id, [name=], role-based. Avoid chained xpath.
"""

COVERAGE_REVIEW_PROMPT = """You are an expert QA engineer reviewing test coverage. Analyze the test results and the original ticket requirements.

Your task:
1. Identify which requirements from the ticket are NOT covered by existing tests.
2. Identify tests that failed and suggest fixes.
3. Only suggest additional tests for ACTUAL requirements from the ticket that are missing. Do NOT suggest trivial tests like verifying individual element existence, button presence, or table structure unless the ticket specifically requires them.

Output your analysis as JSON with this structure:
{
    "covered_requirements": ["list of requirements that are tested"],
    "missing_requirements": ["list of requirements from the ticket NOT tested"],
    "failed_test_analysis": [{"test_name": "...", "failure_reason": "...", "suggested_fix": "..."}],
    "additional_test_scenarios": ["description of each additional test to write — only for genuine missing ticket requirements"]
}

Output ONLY valid JSON, no markdown or explanation.
"""

MISSING_TESTS_PROMPT = """You are an expert QA automation engineer. Based on the coverage review, generate additional Playwright tests in Python using pytest-playwright to cover the missing scenarios.

Rules:
1. Generate ONLY the NEW tests - do not repeat existing tests.
2. Follow the same coding style as the existing tests.
3. Cover ONLY the missing ticket requirements identified. Do NOT add trivial element-existence tests.
4. Include fixes for any failed tests.
5. Output ONLY valid Python code, no markdown or explanations.

CRITICAL FIXTURE RULES — same as always:
- Do NOT define a `page` fixture. The conftest.py already provides a pre-authenticated `page` fixture.
- Do NOT define a `browser`, `browser_context`, or `authed_context` fixture.
- Do NOT navigate to the login page — the browser is already authenticated.
- Use relative paths: page.goto("/path"). The base URL is already configured.
- ONLY import from: pytest, playwright.sync_api.
"""


# All models are served via Copilot API (api.githubcopilot.com) using OAuth token.
# This set is checked to route through the Copilot client.
_COPILOT_API_MODELS = {
    # Claude
    'claude-sonnet-4.6', 'claude-opus-4.6', 'claude-opus-4.7',
    'claude-sonnet-4.5', 'claude-opus-4.5', 'claude-haiku-4.5',
    # GPT
    'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.2', 'gpt-5.2-codex', 'gpt-5.3-codex',
    'gpt-5-mini', 'gpt-4o', 'gpt-4.1', 'gpt-4o-mini',
    # Gemini
    'gemini-3.1-pro-preview', 'gemini-3-flash-preview', 'gemini-2.5-pro',
}


class AIGenerator:
    def __init__(self):
        self._openai_client = None
        self._anthropic_client = None
        self._groq_client = None
        self._github_client = None
        self._copilot_client = None
        self._copilot_token_used = None  # track to detect refresh

    def _get_openai(self):
        if not self._openai_client:
            import openai
            self._openai_client = openai.OpenAI(api_key=config.openai_api_key)
        return self._openai_client

    def _get_anthropic(self):
        if not self._anthropic_client:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        return self._anthropic_client

    def _get_groq(self):
        if not self._groq_client:
            import openai
            self._groq_client = openai.OpenAI(
                api_key=config.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        return self._groq_client

    def _get_github(self):
        if not self._github_client:
            import openai
            self._github_client = openai.OpenAI(
                api_key=config.github_token,
                base_url="https://models.inference.ai.azure.com",
                timeout=180.0,
            )
        return self._github_client

    def _get_copilot(self):
        """Get OpenAI client pointing at Copilot API with a fresh session token."""
        import openai
        token = get_copilot_token()
        # Recreate client if token changed (refreshed)
        if self._copilot_client is None or self._copilot_token_used != token:
            self._copilot_client = openai.OpenAI(
                api_key=token,
                base_url=COPILOT_API_BASE,
                timeout=180.0,
                default_headers={"Editor-Version": "vscode/1.100.0"},
            )
            self._copilot_token_used = token
        return self._copilot_client

    # Models that need max_completion_tokens instead of max_tokens
    _COMPLETION_TOKEN_MODELS = {'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.2', 'gpt-5-mini'}
    # Reasoning models that don't support temperature
    _REASONING_MODELS = {'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.2', 'gpt-5-mini'}
    # Claude models — use max_tokens
    _CLAUDE_MODELS = {'claude-sonnet-4.6', 'claude-opus-4.6', 'claude-opus-4.7',
                      'claude-sonnet-4.5', 'claude-opus-4.5', 'claude-haiku-4.5'}

    def _call_ai(self, system: str, user: str) -> str:
        last_err = None
        for attempt in range(3):
            try:
                return self._call_ai_once(system, user)
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                # Retry on transient network errors only
                if any(k in err_str for k in ['connection', 'timeout', 'getaddrinfo', 'dns', 'temporary']):
                    wait = 5 * (attempt + 1)
                    time.sleep(wait)
                    continue
                raise  # non-transient error, don't retry
        raise last_err  # all retries exhausted

    def _call_ai_once(self, system: str, user: str) -> str:
        if config.ai_provider == "github":
            model = config.github_model
            use_copilot = model in _COPILOT_API_MODELS

            if use_copilot:
                client = self._get_copilot()
            else:
                client = self._get_github()

            # Build token limit kwarg
            if model in self._CLAUDE_MODELS:
                token_kwarg = {"max_tokens": 8000}
            elif model in self._COMPLETION_TOKEN_MODELS:
                token_kwarg = {"max_completion_tokens": 4000}
            else:
                token_kwarg = {"max_tokens": 8000}

            # Reasoning models don't accept temperature
            if model not in self._REASONING_MODELS:
                token_kwarg["temperature"] = 0.2

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **token_kwarg,
            )
            return response.choices[0].message.content.strip()

        elif config.ai_provider == "groq":
            client = self._get_groq()
            response = client.chat.completions.create(
                model=config.groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=8000,
            )
            return response.choices[0].message.content.strip()

        elif config.ai_provider == "openai":
            client = self._get_openai()
            response = client.chat.completions.create(
                model=config.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=8000,
            )
            return response.choices[0].message.content.strip()

        elif config.ai_provider == "anthropic":
            client = self._get_anthropic()
            response = client.messages.create(
                model=config.anthropic_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=8000,
            )
            return response.content[0].text.strip()

        else:
            raise ValueError(f"Unknown AI provider: {config.ai_provider}")

    def generate_tests(self, ticket_text: str, base_url: str = "", page_context: str = "", code_context: str = "") -> str:
        """Generate Playwright test code from Jira ticket details + real page DOM + code changes."""

        def _build_prompt(code_ctx: str = "") -> str:
            context_block = ""
            if page_context:
                context_block += f"""

## REAL PAGE DOM SNAPSHOTS (from crawling the actual app)
Use ONLY the selectors, button labels, link text, and form fields shown below.
Do NOT invent selectors or element text that does not appear in these snapshots.
If a required element is not visible in the snapshots, write the test to verify its absence.

{page_context}
"""
            if code_ctx:
                context_block += f"""

## CODE CHANGES (from repository commits linked to this ticket)
Use these code changes to understand WHAT was implemented and HOW.
- Check the exact selectors, CSS classes, and element IDs used in the code
- Understand conditional logic (v-if, permissions, feature flags) to write both positive and negative tests
- If the code shows a dropdown menu or modal, test the interaction pattern used in the code

{code_ctx}
"""
            return f"""Generate comprehensive Playwright tests for the following Jira ticket.

Target application base URL: {base_url or 'http://localhost:3000'}

## Jira Ticket
{ticket_text}
{context_block}
Generate a complete test file with all necessary imports and test functions.
Use ONLY selectors that appear in the DOM snapshots above. Do NOT guess or hallucinate selectors.
Cover all requirements, acceptance criteria, and reasonable edge cases."""

        # Try with code context first, then truncate/drop if too large
        user_prompt = _build_prompt(code_context)
        try:
            code = self._call_ai(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            err_str = str(e).lower()
            if "413" in err_str or "too large" in err_str or "tokens_limit" in err_str:
                # Retry with truncated code context (half)
                if code_context and len(code_context) > 500:
                    half = code_context[:len(code_context) // 3]
                    user_prompt = _build_prompt(half)
                    try:
                        code = self._call_ai(SYSTEM_PROMPT, user_prompt)
                    except Exception as e2:
                        if "413" in str(e2).lower() or "too large" in str(e2).lower():
                            # Drop code context entirely
                            user_prompt = _build_prompt("")
                            code = self._call_ai(SYSTEM_PROMPT, user_prompt)
                        else:
                            raise
                else:
                    # No code context to drop — retry without it
                    user_prompt = _build_prompt("")
                    code = self._call_ai(SYSTEM_PROMPT, user_prompt)
            else:
                raise

        code = self._strip_code_fences(code)

        # Validate AI actually produced test code
        if not code or len(code.strip()) < 50 or 'def test_' not in code:
            raise RuntimeError(
                f"AI returned empty or invalid test code ({len(code)} chars). "
                f"Model '{config.github_model}' may have hit its output token limit. "
                f"Try a model with higher limits like gpt-4o or gpt-4.1."
            )

        return code

    def review_coverage(self, ticket_text: str, test_code: str, test_results: str) -> dict:
        """Review test coverage and identify gaps."""
        user_prompt = f"""## Original Ticket
{ticket_text}

## Generated Test Code
```python
{test_code}
```

## Test Execution Results
{test_results}

Analyze the coverage and identify what's missing."""

        result = self._call_ai(COVERAGE_REVIEW_PROMPT, user_prompt)
        result = self._strip_code_fences(result)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "covered_requirements": [],
                "missing_requirements": ["Could not parse AI response"],
                "missing_edge_cases": [],
                "failed_test_analysis": [],
                "additional_test_scenarios": [],
                "raw_response": result,
            }

    def generate_missing_tests(self, ticket_text: str, existing_code: str, coverage_review: dict, base_url: str = "") -> str:
        """Generate additional tests to cover gaps identified in review."""
        user_prompt = f"""## Original Ticket
{ticket_text}

## Existing Tests
```python
{existing_code}
```

## Coverage Review
{json.dumps(coverage_review, indent=2)}

Target application base URL: {base_url or 'http://localhost:3000'}

Generate ONLY the additional test functions needed to cover the missing scenarios.
Include necessary imports at the top if new ones are needed."""

        code = self._call_ai(MISSING_TESTS_PROMPT, user_prompt)
        code = self._strip_code_fences(code)
        return code

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown code fences from AI output."""
        lines = text.split("\n")
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
