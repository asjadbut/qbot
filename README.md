# QBot — AI-Powered Test Automation from Jira

A cross-platform desktop app (Windows, macOS, Linux) that generates and runs Playwright tests from Jira tickets using AI.

## How It Works

```
Jira Ticket → Crawl Target Pages → Fetch Code Changes → AI Generates Tests → Lint + Auto-Fix → Playwright Executes → AI Repairs Failures → Results
```

1. **Fetch** a Jira ticket (Cloud or Server/DC)
2. **Crawl** the target app pages mentioned in the ticket — captures real DOM (buttons, inputs, links, selectors), expands dropdown menus, and takes ARIA accessibility snapshots. Cached per ticket for fast re-runs.
3. **Fetch code changes** from Bitbucket using the ticket key (e.g. PDM-7200) — finds linked commits and extracts diffs
4. **AI generates** Playwright tests using ticket requirements, real page structure, and actual code changes
5. **Lint** the generated code against the crawled DOM — hallucinated selectors and known-bad patterns are flagged and auto-fixed by a targeted AI call before execution
6. **Playwright executes** the tests in Google Chrome with saved auth state (flaky failures retried once)
7. **AI repairs failures** — failing tests + their real error output go back to the model for a fix, then re-run (up to 2 rounds)
8. **Results** displayed with pass/fail per test, human-readable failure explanations, and raw pytest output

---

## Quick Start

### Prerequisites

- Python 3.12+
- Google Chrome (optional — falls back to Playwright's bundled Chromium)
- GitHub Copilot subscription (org or individual)
- OS: Windows, macOS, or Linux

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### Run

```bash
python main.py
```

The pre-built [QBot.exe](https://github.com/asjadbut/qbot/releases/download/v1.0.0/QBot.exe) (~70 MB standalone, no Python required) from the [latest release](https://github.com/asjadbut/qbot/releases/tag/v1.0.0) is **Windows-only**. On macOS and Linux, run from source as shown above (or build a native binary — see [Build](#build)).

---

## Configuration

### GitHub Copilot Authorization

QBot uses the GitHub Copilot API via OAuth — the same API that powers VS Code Copilot Chat.

1. Open QBot **Settings** (gear icon)
2. Click **Authorize Copilot** → browser opens to `github.com/login/device`
3. Enter the code shown, click **Authorize**
4. QBot stores the OAuth token and refreshes it automatically

No PAT required. Authorization persists across app restarts.

### Available AI Models

| Model | Context | Notes |
|-------|---------|-------|
| `claude-sonnet-4.6` | 200K | Recommended — fast, high quality |
| `claude-opus-4.6` / `4.7` | 200K | Most capable Claude |
| `claude-sonnet-4.5` / `opus-4.5` | 200K | Previous generation |
| `claude-haiku-4.5` | 200K | Fastest Claude |
| `gpt-5.5` / `gpt-5.4` | 272K | Latest GPT |
| `gpt-5.2` / `gpt-5-mini` | 272K | GPT 5 family |
| `gpt-4o` / `gpt-4.1` | 64–128K | Reliable all-rounders |
| `gemini-3.1-pro-preview` | 200K | Google Gemini |
| `gemini-2.5-pro` | 128K | Previous Gemini |

Select a model from the dropdown in Settings.

### Jira Connection

| Jira Type | URL Format | Password Field |
|-----------|-----------|----------------|
| **Cloud** | `yoursite.atlassian.net` | API Token ([generate here](https://id.atlassian.com/manage-profile/security/api-tokens)) |
| **Server/DC** | `https://jira.company.com` | Password or PAT |

Check **Remember credentials** to auto-fill on next launch.

### Target URLs

Add your app URLs in **Settings → Target Application URLs**. These populate the URL dropdown in the ticket view so you don't have to type them each time.

---

## Pipeline Details

### Crawl

- Opens Google Chrome with anti-detection (spoofed `navigator.webdriver`, custom user agent)
- If a login page is detected, waits up to 5 minutes for you to log in
- Saves auth state (`auth_state.json`) for reuse during test execution
- Captures page snapshots: headings, buttons, inputs, links, forms, visible text, and `data-testid` attributes
- **Expands dropdown menus**: clicks visible dropdown toggles (`.dropdown-toggle`, `data-toggle`, `aria-haspopup`) and records the revealed menu items — so the AI knows which links are hidden until a toggle is clicked, and which interaction pattern to use
- **ARIA snapshots**: captures the accessibility tree (roles + names) per page, enabling robust `get_by_role()` locators
- Recognises production/staging URL variants in tickets and rewrites to your target host
- **Per-ticket cache**: crawl snapshots + Bitbucket context are cached for 60 minutes (in the QBot data directory, e.g. `%APPDATA%\QBot\cache\` on Windows). Re-running the same ticket skips the crawl entirely — no Chrome window, no re-login — as long as the saved auth state still exists

### Code Context (Bitbucket)

- After crawling, searches Bitbucket Cloud for commits matching the Jira ticket key (e.g. `PDM-7200`)
- Scans commit messages across recent history and merged pull requests
- Filters out merge/sync commits ("Merged in...", "Merge branch...") that contain no real changes
- Extracts unified diffs, filtering out non-code files (minified JS, lock files, images, migrations, build artifacts)
- Up to 10 commits, 10K chars per diff, 30K total \u2014 fits within Copilot API's 200K context window
- Code diffs help the AI understand implementation details: conditional logic, selectors, feature flags, and permission checks

### AI Test Generation

- Sends ticket text + real page context + code diffs to the selected AI model
- Generated tests use actual selectors from the crawled pages and understand implementation details from code changes
- The AI's mindset is driven by the active **Team Profile** (see [Team Profiles](#team-profiles) below) so different teams can use different style rules, tech-stack hints, selector conventions and product glossaries
- **Token budgeting**: prompt size is estimated up front and contexts are trimmed *before* sending (priority: ticket > page DOM > code diffs). Code context is trimmed by dropping whole commit-diff sections, never by slicing mid-hunk
- Strips AI-generated fixture redefinitions (AST-based) to avoid conflicts with conftest
- Validates output contains `def test_` and parses as valid Python — a truncated completion triggers one "be more concise" retry instead of failing later at pytest collection
- Auto-fallback: if the model still reports the prompt is too large or returns no choices, truncates code context progressively (full → 1/3 → none)

### Lint + Auto-Fix

Before any test executes, the generated code is checked by a deterministic linter (`test_linter.py`) against the crawled DOM snapshots:

- **Errors** (definitely wrong): `to_have_title()`, `to_have_url("/relative")`, `.check()`/`.is_checked()` on elements the snapshot proves are not native checkboxes
- **Warnings** (suspicious): exact `to_have_count(N)` with guessed numbers, `#id` / `[name=]` / `text=` / `get_by_text()` referencing selectors or text never seen in any crawled page (hallucination detection)
- Flagged issues are sent to the AI in one targeted fix call along with the DOM snapshots; the corrected file replaces the original. If the fix fails, the original code is kept — the linter never blocks the pipeline

### Test Execution

- Runs via `pytest` with `-v --tb=short -p no:playwright --junitxml=...`
- Uses the correct Python interpreter (`sys.executable` from source; `python` on PATH from the frozen exe)
- Reuses auth state from crawl step (usually no second login needed)
- Each test gets a fresh browser tab in the shared authenticated context
- **Flaky-failure retries**: when `pytest-rerunfailures` is installed, failed tests are retried once (`--reruns 1 --reruns-delay 2`) so transient timing failures don't reach the repair loop
- Results parsed from **JUnit XML** (structured, reliable) with regex parsing of console output as fallback
- Failed tests show human-readable failure explanations (e.g. "Timed out after 30s — the element exists but is not visible") plus the full traceback for the repair loop
- Raw pytest output shown in Test Results tab for debugging failures

### AI Repair Loop (Self-Healing)

If any tests fail after execution:

- Failing tests + their actual pytest errors + the DOM snapshots are sent back to the model
- The model fixes **only** the failing tests (passing tests are kept verbatim) — or deletes a test if the DOM proves its assertion can never pass
- The repaired file is re-executed; up to **2 repair rounds**, stopping early when everything passes
- Repaired code is AST-validated; any bad output keeps the previous version, so the pipeline never regresses

### Replay

After pipeline completes, click **▶ Replay Tests** to re-run without regenerating.

---

## Team Profiles

Different QA teams write tests differently. Some want every edge case covered. Some, like the team this app started with, want only what the ticket explicitly requires. Some apps are ASP.NET WebForms with full postbacks; others are Vue SPAs with client-side routing. **Team Profiles** let each team capture their own QA mindset, tech-stack hints, selector conventions and product glossary, and have QBot generate tests in their style — no code changes required.

### How it works

The system prompt sent to the AI is composed at runtime:

```
[Immutable BASE rules]      ← protect pipeline contract (fixtures, output format,
                              checkbox handling, count rules, navigation, etc.)
[Active profile sections]   ← style rules, tech stack, selector conventions,
                              glossary, extra instructions  (team-editable)
```

The BASE rules are hard-coded and cannot be removed by users — they exist to keep the AI's output compatible with the runner pipeline (the conftest, the parser, the auth contract). The team-editable sections sit on top and shape *how* the AI writes tests within those constraints.

### Where profiles live

In the QBot data directory, as `profiles.json`. The default profile is auto-seeded on first run with the original QBot prompt content split into editable sections, so existing users see no behavioural change until they edit it.

The data directory is per-OS:

| OS | Location |
|----|----------|
| **Windows** | `%APPDATA%\QBot\` |
| **macOS** | `~/Library/Application Support/QBot/` |
| **Linux** | `$XDG_CONFIG_HOME/QBot/` (fallback `~/.config/QBot/`) |

### Editor UI

**Settings → Team Profile → Manage Profiles…** opens the profile editor. The list on the left shows all profiles; the form on the right edits the selected one. Use **+ New** for a blank slate or **Clone** to start from an existing profile (recommended — clone the Default and tweak from there).

Each profile has five editable sections:

| Section | Purpose |
|---|---|
| **Style Rules** | Your team's QA mindset. Verbose vs minimal scope, when to write negative cases, what kinds of tests to never generate. One bullet per line. |
| **Tech Stack & App-Specific Patterns** | Framework quirks the AI must respect. ASP.NET postback waits, Vue v-if removal, Next.js client-side nav, etc. |
| **Selector & Interaction Conventions** | Preferred locator strategy (data-testid, role-based, legacy IDs). How custom checkboxes/dropdowns behave in your app. |
| **Product Glossary** | Domain terms the AI should know. `term — definition`, one per line. |
| **Extra Instructions** | Anything else: feature flags, env-specific behaviour, do/don't lists. |

Switch the **Active** profile in the Settings → Team Profile card. Saving the dialog applies the new profile to the next test generation.

### Building a profile from your team's history

The fastest way to get a profile that matches your team's style is to derive it from real artifacts: Jira tickets your team has shipped, plus the test plans your QA wrote for them. Below are three example prompts you can paste into any chat-capable AI model (Copilot Chat, Claude, ChatGPT) along with your tickets/test plans. The model returns text you paste into the matching profile section.

These examples are intentionally generic — replace the bracketed parts with your team's product names, frameworks and conventions.

---

#### Prompt 1 — Generate **Style Rules** from past tickets and test plans

> I'm giving you several Jira tickets and the test cases our QA team wrote for those tickets. Read both carefully and infer our QA's mindset and priorities, then output a list of bullet-style rules describing how this QA writes tests. Focus on:
>
> - How they decide test scope (every requirement vs only obvious ones)
> - The ratio of tests to ticket requirements they aim for
> - What kinds of tests they explicitly avoid
> - When they include negative / edge-case tests
> - How they decide whether something is "in scope" for the change
>
> Style your output as a concise bullet list, one rule per line, with `NEVER:` prefixes for hard prohibitions. Keep it under 30 bullets. Do not invent generic best practices — only include rules that are actually visible in the QA's behaviour across these tickets.
>
> ### Example output style
>
> ```
> - Generate ONLY tests that directly verify the requirements stated in the Jira ticket. Do NOT invent extra tests beyond the ticket scope.
> - Count the distinct requirements in the ticket. Your test count should be CLOSE to that number (±2). If a ticket has 8 requirements, generate roughly 8-10 tests — NOT 19 or 36.
> - Each ticket requirement = roughly ONE test. If a requirement says "add 7 new voices", write ONE test that checks all 7.
> - Focus on FUNCTIONAL behavior: can the user perform the actions described? Do the changes work as specified?
> - Include negative/edge case tests ONLY when they are meaningful for the specific feature.
> - NEVER: Individual tests for each item in a list — write ONE test that checks all items.
> - NEVER: Tests that verify standard buttons (Save, Cancel) exist.
> - NEVER: Tests that verify table structure, column counts, header rows, or heading existence.
> - NEVER: Tests that check element attributes (voiceid, href, class) unless the ticket specifies them.
> - NEVER: Tests for sorting/ordering unless the ticket says items must be sorted.
> - NEVER: "Cancel button discards changes" tests unless the ticket mentions cancel behavior.
> - NEVER: Negative/edge case tests for behavior NOT described in the ticket.
> ```
>
> ### Tickets and test plans
>
> ```
> [Paste ticket 1 + its test plan]
> [Paste ticket 2 + its test plan]
> ...
> ```

Paste the model's output into the **Style Rules** section of your profile.

---

#### Prompt 2 — Generate **Selector & Interaction Conventions** from your codebase

> I'm giving you snippets from our front-end codebase (templates / components / a few page sources) and a couple of existing Playwright tests. Identify our team's preferred locator strategies and interaction patterns and output them as a set of rules an AI should follow when writing new Playwright tests for this app. Cover at least:
>
> - Preferred locator strategy (`data-testid` vs `role` vs legacy `#id` vs class)
> - How custom form components behave (checkboxes, dropdowns, modals) — native or custom-rolled?
> - Wait/settle patterns we already use (`wait_for_load_state`, `wait_for_url`, fixed timeouts)
> - Navigation patterns: do menus use `v-if` removal, CSS hide, or full re-render?
> - Common access-restriction behaviour (redirect vs error message)
>
> Produce concrete `GOOD:` / `BAD:` code examples wherever a rule is non-obvious. Keep it grouped under short ALL-CAPS headers.
>
> ### Example output style
>
> ```
> ROBUST TEST PATTERNS — follow these to avoid flaky tests:
> - After page.goto(), always call page.wait_for_load_state("domcontentloaded") before assertions.
> - After clicking a button that submits a form, use page.wait_for_load_state("load") or page.wait_for_url() — the page may navigate.
> - When testing access restrictions, the app usually REDIRECTS rather than showing "Access Denied" text.
>     GOOD: assert "/expected" in page.url
>     BAD:  expect(page.locator("text=Access Denied")).to_be_visible()
> - Use page.wait_for_timeout(1000) sparingly after async actions/animations.
> - Prefer expect() with timeout for assertions that may need the page to settle:
>     expect(page.locator(...)).to_be_visible(timeout=10000)
>
> CHECKBOX HANDLING — critical:
> - is_checked(), to_be_checked(), check(), uncheck() ONLY work on native <input type="checkbox">.
> - For custom checkbox components (divs/spans with classes like ".voice-checkbox"), use .click() to toggle and class/aria checks for state:
>     GOOD: page.locator(".voice-checkbox").first.click()
>     GOOD: assert "checked" in page.locator(".voice-checkbox").first.get_attribute("class")
>     BAD:  page.locator(".voice-checkbox").first.is_checked()
>
> NAVIGATION MENUS & DROPDOWNS:
> - CSS-hidden nav menus (sidebar/top nav links) — often invisible, do NOT click/hover them, just check the DOM with locator counts.
> - Bootstrap/Vue dropdown BUTTONS (e.g. class="dropdown-toggle") — visible, click to reveal items:
>     page.locator("button:has-text('Select an Action')").click()
>     page.wait_for_timeout(500)
>     expect(page.locator("a:has-text('Roster History')").first).to_be_visible()
> - For Vue v-if conditionally rendered links, the element is removed from the DOM — use to_have_count(0) to verify absence.
> - NEVER invent UI elements. Only reference selectors and text that appear in the provided DOM snapshots.
> ```
>
> ### Codebase snippets
>
> ```
> [Paste 2-5 representative templates / components]
> [Paste 1-2 existing Playwright tests written by your team]
> ```

Paste the model's output into the **Selector & Interaction Conventions** section of your profile.

---

#### Prompt 3 — Generate **Tech Stack & App-Specific Patterns**

> I'm giving you a description of our application's tech stack (framework, server-side patterns, anything unusual). Produce a list of framework quirks an AI must respect when writing Playwright tests for our app. For each quirk, give one or two `GOOD:` / `BAD:` code examples showing the right and wrong wait/interaction pattern. Keep it grouped under a short ALL-CAPS header.
>
> ### Example output style
>
> ```
> ASP.NET / LEGACY WEB APP PATTERNS — this app uses ASP.NET WebForms:
> - After clicking Save/Submit/Delete buttons (e.g. #btnSaveAuthentication), the page does a full postback. ALWAYS add page.wait_for_load_state("networkidle") THEN page.wait_for_timeout(2000) to let the server process before navigating away.
>     GOOD: page.locator("#btnSave").click(); page.wait_for_load_state("networkidle"); page.wait_for_timeout(2000)
>     BAD:  page.locator("#btnSave").click(); page.wait_for_load_state("load")
> - Settings/config changes (enabling checkboxes, changing dropdowns) take effect on the SERVER after the postback completes. If you navigate to another page too early, the setting won't be active yet.
> - When a test enables a setting, saves, and then checks the effect on another page, add sufficient wait after save before navigating.
> ```
>
> ### Other examples of frameworks and the kinds of quirks I expect to see
>
> - **Vue 3 + `<v-if>`** — conditional elements are REMOVED from the DOM, not just hidden. Use `to_have_count(0)` to verify absence; `to_be_hidden()` will fail because the element doesn't exist.
> - **Next.js client-side nav** — `page.goto()` triggers full SSR, but in-app `<Link>` clicks don't. After clicking a `<Link>`, use `page.wait_for_url()` instead of `wait_for_load_state("load")`.
> - **React Server Components** — server actions complete via `fetch`, not navigation. Wait for the network response or for the resulting DOM change.
> - **Single-Page Apps with optimistic updates** — UI changes before the server confirms. Re-fetch / reload after a save to verify persistence, don't trust the immediate UI state.
>
> ### Our tech stack
>
> ```
> [Describe your app: framework, server-side patterns, auth model, anything unusual]
> ```

Paste the model's output into the **Tech Stack & App-Specific Patterns** section of your profile.

---

### Tips for tuning a profile

- **Clone the Default** before editing. It contains rules forged from real test failures over many iterations — keep them as your starting baseline.
- **One failure → one rule.** Each time a generated test fails for a reason that wasn't in your profile, add a `GOOD:` / `BAD:` example for it. The Default profile in this repo was built exactly this way.
- **Concrete examples beat abstract rules.** `BAD: locator.is_checked() on a custom span` is far more effective than "be careful with checkboxes."
- **Don't fight the BASE rules.** If a generated test fails because of a contract violation (fixture redefined, code fence in output, etc.), that's a bug to file — don't try to override it from a team profile.
- **Test profiles by re-generating an old ticket.** Pick a ticket your team has already shipped and run QBot against it twice — once with Default, once with your new profile. Diff the outputs.

---

## Browser

QBot uses **Google Chrome** with anti-detection flags when it can find it, probing the standard install locations per OS:

- **Windows**: `Program Files\Google\Chrome`, `Program Files (x86)`, and `%LOCALAPPDATA%`
- **macOS**: `/Applications/Google Chrome.app`
- **Linux**: `google-chrome` / `chromium` on `PATH`, plus common `/usr/bin` and `/snap/bin` locations

If Chrome is not found, QBot falls back to Playwright's bundled Chromium.

---

## Security & Privacy

### Credentials Are Never Sent to the AI

QBot uses several credentials:

| Credential | Purpose | Sent to AI? |
|------------|---------|-------------|
| **GitHub OAuth token** | Authenticates with Copilot API | **No** — used only as HTTP `Authorization` header |
| **Jira credentials** | Fetches ticket data from Jira REST API | **No** — used only for Jira API authentication |
| **Bitbucket API token** | Fetches code diffs from Bitbucket | **No** — used only for Bitbucket API auth |
| **Browser auth state** | Replays logged-in sessions in Playwright | **No** — used only by the local browser |

**What IS sent to the AI:** Only the Jira ticket text (summary, description, acceptance criteria, comments), DOM snapshots from crawled pages, and code diffs from linked commits. No tokens, passwords, cookies, or session data are ever included in AI prompts.

### Credential Storage

- **Location:** The QBot data directory (`settings.json` and `copilot_token.json`), user-scoped and not shared. Per-OS: `%APPDATA%\QBot\` (Windows), `~/Library/Application Support/QBot/` (macOS), `~/.config/QBot/` (Linux)
- **Format:** Plaintext JSON (protected by OS user-level file permissions)
- **Jira password:** Only saved if you check "Remember credentials" — otherwise discarded after login
- **Copilot OAuth token:** Persisted across restarts, auto-refreshes session tokens (~30 min)
- **Browser auth state:** Saved as `auth_state.json` in the generated tests directory (contains session cookies from the target app, not QBot credentials)

### What QBot Does NOT Do

- Does not send credentials to any third party beyond their intended API endpoint
- Does not log, print, or write credentials to console or log files
- Does not include credentials in generated test code
- Does not transmit credentials in error messages or stack traces

---

## Settings

Stored as `settings.json` in the QBot data directory (`%APPDATA%\QBot\` on Windows, `~/Library/Application Support/QBot/` on macOS, `~/.config/QBot/` on Linux). Access via the gear icon.

---

## Build

```bash
python build.py
```

Produces a standalone artifact in the `dist/` folder, matching your OS:

| OS | Artifact |
|----|----------|
| **Windows** | `QBot.exe` (~80 MB) |
| **macOS** | `QBot.app` |
| **Linux** | `QBot` binary |

Build on the OS you want to target (PyInstaller does not cross-compile). Pre-built Windows releases are published at [github.com/asjadbut/qbot/releases](https://github.com/asjadbut/qbot/releases/tag/v1.0.0).

---

## Project Structure

```
qbot/
  config.py           # Runtime config dataclass
  paths.py            # Cross-platform data directory + Chrome location helpers
  settings.py         # JSON persistence (per-OS QBot data directory)
  copilot_auth.py     # GitHub Copilot OAuth device flow + token management
  ai_generator.py     # AI prompt + Copilot API calls, token budgeting, repair/lint-fix calls
  profiles.py         # Team Profiles — per-team style/tech/selector/glossary
  test_linter.py      # Deterministic linter — validates generated code against crawled DOM
  context_cache.py    # Per-ticket cache for crawl snapshots + Bitbucket context
  bitbucket_client.py # Bitbucket Cloud commit/diff fetching
  page_crawler.py     # Playwright crawler, URL extraction, DOM/ARIA snapshots, menu expansion
  test_runner.py      # pytest execution, conftest generation, JUnit XML result parsing
  jira_client.py      # Jira Cloud/Server ticket fetching
  ui/
    app.py            # Main window, view transitions
    login_view.py     # Jira login screen
    ticket_view.py    # Ticket input, URL/model selection
    runner_view.py    # Pipeline execution (crawl→generate→lint→execute→repair), live log, results
    settings_dialog.py # Settings modal with Copilot auth + active profile picker
    profiles_dialog.py # Team Profiles editor (list + form)
    styles.py         # VS Code Dark color palette, fonts
```

---

## Development History

QBot was built and iteratively improved across AI-assisted sessions starting June 4, 2026, using GitHub Copilot as a pair-programming partner. Features were driven by real-time user testing and feedback.

### Phase 1: Initial Build

Started with a simple prompt to build a desktop app for Jira → AI → Playwright test automation. The AI scaffolded 13 files covering the core pipeline: Jira ticket fetching, AI test generation (OpenAI + Anthropic), pytest execution, and a CustomTkinter UI with login → ticket → runner views.

### Phase 2–8: Settings, Jira Cloud, UI, Browser Management

Rapid iteration on core infrastructure: JSON persistence (`%APPDATA%\QBot`), Jira Cloud auto-detection with proper auth, VS Code Dark theme, Chrome detection with anti-bot stealth, and resolving browser instance conflicts between QBot and pytest-playwright.

### Phase 9: Page Crawler

The biggest quality leap — added `page_crawler.py` to open Chrome, detect login pages, wait for manual auth, and capture real DOM snapshots. AI tests went from hallucinated selectors to using actual page elements.

### Phase 10: GitHub Models API

Simplified from multi-provider (OpenAI/Anthropic/Groq) to GitHub Models API using a PAT with `copilot` scope. Added model dropdown with GPT, Codestral, Llama, DeepSeek variants.

### Phase 11–14: Reliability Fixes

Fixed `networkidle` hangs, malformed URLs from ticket text, Python 3.14 lambda closure breakage, conftest issues, and settings refresh bugs.

### Phase 15–18: Test Output & Polish

Rewrote pytest result parser (regex-based), added URL variant recognition (production → dev rewrites), VS Code-style UI polish, and gitignore.

### Phase 19: Prompt Engineering from Failures

Iteratively improved the AI system prompt based on real test failures. Added GOOD/BAD example sections for: ASP.NET postback timing, page title assertions, URL assertions, hidden nav menus, Bootstrap dropdowns, Vue conditionals, and element count assertions.

### Phase 20: Human-Readable Failure Explanations

Added `_humanize_failure()` to convert raw pytest errors into plain English. Failed tests now show explanations like "Timed out after 30s — the element exists but is not visible."

### Phase 21: Bitbucket Code Context

Added `bitbucket_client.py` to fetch commits and diffs linked to each Jira ticket. Code changes are included in the AI prompt so tests target actual implementation details — not just what's visible in the DOM.

### Phase 22: GitHub Copilot API (June 6, 2026)

Migrated from GitHub Models API (8K token limit) to the Copilot API (`api.githubcopilot.com`) — the same API powering VS Code Copilot Chat. Uses OAuth device flow for authentication. Unlocked Claude Sonnet/Opus (200K context), GPT-5.x (272K context), and Gemini models. No more token limit issues with code context.

### Phase 23: Settings UI & Commit Filtering (June 6, 2026)

Settings dialog centered on screen with separate cards for GitHub Copilot (auth + model) and App Settings (browser + URLs), matching the Bitbucket card style. Bitbucket commit fetching now filters out merge/sync commits (e.g. "Merged in feature/...", "Merge branch '...' into ...") that contain no actual code changes.

### Phase 24: UX Polish & Context Limits (June 6, 2026)

Removed settings button from login screen (accessible only from ticket view). Settings refresh now only triggers on save, not on cancel/close. Input field borders changed from always-blue to subtle gray (blue only on focus). Increased Bitbucket diff limits from 2K/6K to 10K/30K per commit/total and max commits from 5 to 10, taking advantage of the Copilot API's 200K context window for better AI accuracy.

### Phase 25: Team Profiles (June 9, 2026)

Refactored the monolithic system prompt into composable **Team Profiles** stored in `%APPDATA%\QBot\profiles.json`. Each profile has five editable sections (style rules, tech stack, selector conventions, glossary, extra instructions) layered on top of immutable BASE rules that protect the runner pipeline contract. New "Manage Profiles…" editor dialog with new/clone/delete and per-profile editing. The original Paradym-tuned prompt becomes the auto-seeded **Default** profile so existing users see no behavioural change until they edit it.

Hardened the Default profile's BASE rules by adding `GOOD:` / `BAD:` examples for every new failure mode discovered during dogfooding: substring text-match traps (`text=`, `get_by_text`, `filter(has_text=...)` all do substring matching by default), self-contained custom checkboxes that don't wrap a hidden `<input>`, post-Save URL unpredictability, fan-out per-item tests that share state, structural tests for column headers / Save buttons / table skeletons, and `to_have_count(N)` with guessed numbers. Added a final pre-flight checklist at the end of the system prompt to counter the "lost in the middle" attention dip on large prompts.

Also: defensive response extraction (`_extract_openai_text` / `_extract_anthropic_text`) so empty `choices` arrays from the Copilot route raise a meaningful `RuntimeError` instead of `IndexError`; the same error message is matched by the auto-truncate retry path so context-overflow failures recover gracefully. Trimmed the model dropdown to the Claude 4.5 series (Sonnet/Opus/Haiku) — the 4.6/4.7 variants are not consistently available on the Copilot route.

### Phase 26: Accuracy & Efficiency Overhaul (June 11, 2026)

A five-part accuracy push followed by three efficiency upgrades:

**Structured results** — pytest now writes JUnit XML, parsed with stdlib `ElementTree`; the regex console parser remains only as a fallback. Each result carries the full failure traceback, which feeds the repair loop.

**Deterministic linter** (`test_linter.py`) — hard rules that previously lived only as prompt pleas are now enforced in code. Builds an index of every id/name/button/link/menu-item/ARIA string the crawler actually saw, then flags hallucinated selectors, `to_have_title`/`to_have_url("/relative")`, guessed `to_have_count(N)`, and checkbox-API misuse on non-native elements. Flagged issues are auto-fixed by one targeted AI call before execution.

**Self-healing repair loop** — new pipeline step "4. AI Repairs Failures": failing tests + real errors + DOM snapshots go back to the model, which fixes only the failures; repaired tests re-run, bounded to 2 rounds. All AI-returned code is AST-validated with keep-previous-on-failure semantics.

**Token budgeting** — prompt size is estimated up front and contexts trimmed pre-flight (whole diff sections, never mid-hunk), eliminating the wasted fail-then-retry round-trip. Truncated model output (SyntaxError) gets one "be concise" retry.

**Frozen-exe fix** — pytest is launched via `sys.executable` from source / `python` on PATH from the PyInstaller exe.

**Richer crawls** — the crawler now clicks dropdown toggles and records the revealed menu items, captures ARIA accessibility snapshots per page, and prefers `data-testid` selectors. The AI no longer guesses whether a link is hidden inside an unopened menu.

**Flaky-test reruns** — `pytest-rerunfailures` retries each failure once so transient ASP.NET postback timing issues never reach the repair loop as "real" failures.

**Per-ticket context cache** (`context_cache.py`) — crawl snapshots + Bitbucket context are cached for 60 minutes keyed by ticket + target URL. Re-running the same ticket skips the crawl and Bitbucket fetch entirely.

---

### Key Lessons Learned

1. **Real page context eliminates hallucination** — Crawling actual DOM snapshots was the single biggest quality improvement.
2. **Concrete examples > abstract rules** — GOOD/BAD code examples in the AI prompt are far more effective than instructions like "don't use exact counts."
3. **Iterative prompt improvement beats one-shot** — Each test failure reveals a pattern; adding examples for each creates a feedback loop.
4. **Code context from VCS matters** — Bitbucket diffs help the AI understand implementation details not visible in the DOM.
5. **`networkidle` is unreliable** — Modern SPAs never reach network idle. Use `load` + settle delay.
6. **API token limits vary wildly** — GitHub Models API has 8K input limit; Copilot API has 200K+. Choose the right endpoint.
7. **One generic prompt does not fit every team** — Different products, different stacks, different QA cultures. Splitting the prompt into a fixed runner contract + a team-editable profile lets each team carry their own mindset without forking the tool.
8. **The end of the prompt gets the most attention** — On long prompts, models suffer a "lost in the middle" attention dip. A short pre-flight checklist at the very end catches the rules they would otherwise skip.
9. **Defensive parsing on AI responses** — Empty `choices` arrays surface as opaque `IndexError`s. Extract text through a helper that raises a meaningful error AND signals the retry path to truncate context.
10. **Enforce hard rules in code, not prose** — No matter how emphatic the prompt, models still occasionally emit forbidden patterns. A deterministic linter that validates against the crawled DOM catches what the prompt misses, and one targeted fix call is cheaper than a failed test run.
11. **Real error output is the best repair prompt** — Feeding failing tests back with their actual tracebacks + DOM snapshots fixes most failures in one round; bounding the loop prevents token burn on unfixable tests.
12. **Count tokens before sending, not after failing** — A pre-flight token estimate plus structure-aware trimming (drop whole diff sections, never mid-hunk) replaces an entire wasted API round-trip.
