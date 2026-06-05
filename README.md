# QBot — AI-Powered Test Automation from Jira

A Windows desktop app that generates and runs Playwright tests from Jira tickets using AI.

## How It Works

```
Jira Ticket → Crawl Target Pages → Fetch Code Changes → AI Generates Tests → Playwright Executes → Results
```

1. **Fetch** a Jira ticket (Cloud or Server/DC)
2. **Crawl** the target app pages mentioned in the ticket — captures real DOM (buttons, inputs, links, selectors)
3. **Fetch code changes** from Bitbucket using the ticket key (e.g. PDM-7200) — finds linked commits and extracts diffs
4. **AI generates** Playwright tests using ticket requirements, real page structure, and actual code changes
5. **Playwright executes** the tests in Google Chrome with saved auth state
6. **Results** displayed with pass/fail per test, human-readable failure explanations, and raw pytest output

---

## Quick Start

### Prerequisites

- Python 3.12+
- Google Chrome
- GitHub Copilot subscription (org or individual)

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### Run

```bash
python main.py
```

Or use the pre-built `dist/QBot.exe`.

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
- Captures page snapshots: headings, buttons, inputs, links, forms, visible text
- Recognises production/staging URL variants in tickets and rewrites to your target host

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
- Strips AI-generated fixture redefinitions (AST-based) to avoid conflicts with conftest
- Validates output contains `def test_` before proceeding
- Auto-fallback: if prompt is too large, truncates code context progressively

### Test Execution

- Runs via `pytest` with `-v --tb=short -p no:playwright`
- Reuses auth state from crawl step (usually no second login needed)
- Each test gets a fresh browser tab in the shared authenticated context
- Results parsed from pytest output: pass/fail counts + individual test names
- Failed tests show human-readable failure explanations (e.g. "Timed out after 30s — the element exists but is not visible")
- Raw pytest output shown in Test Results tab for debugging failures

### Replay

After pipeline completes, click **▶ Replay Tests** to re-run without regenerating.

---

## Browser

QBot uses **Google Chrome** with anti-detection flags. If Chrome is not found, falls back to Playwright's bundled Chromium.

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

- **Location:** `%APPDATA%\QBot\settings.json` and `copilot_token.json` (user-scoped, not shared)
- **Format:** Plaintext JSON (protected by Windows user-level file permissions)
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

Stored at `%APPDATA%\QBot\settings.json`. Access via the gear icon.

---

## Build

```bash
python build.py
```

Produces `dist/QBot.exe` (~80 MB standalone).

---

## Project Structure

```
qbot/
  config.py           # Runtime config dataclass
  settings.py         # JSON persistence (%APPDATA%\QBot\)
  copilot_auth.py     # GitHub Copilot OAuth device flow + token management
  ai_generator.py     # AI prompt + Copilot API calls
  bitbucket_client.py # Bitbucket Cloud commit/diff fetching
  page_crawler.py     # Playwright crawler, URL extraction, DOM snapshots
  test_runner.py      # pytest execution, conftest generation, result parsing
  jira_client.py      # Jira Cloud/Server ticket fetching
  ui/
    app.py            # Main window, view transitions
    login_view.py     # Jira login screen
    ticket_view.py    # Ticket input, URL/model selection
    runner_view.py    # Pipeline execution, live log, results display
    settings_dialog.py # Settings modal with Copilot auth
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

---

### Key Lessons Learned

1. **Real page context eliminates hallucination** — Crawling actual DOM snapshots was the single biggest quality improvement.
2. **Concrete examples > abstract rules** — GOOD/BAD code examples in the AI prompt are far more effective than instructions like "don't use exact counts."
3. **Iterative prompt improvement beats one-shot** — Each test failure reveals a pattern; adding examples for each creates a feedback loop.
4. **Code context from VCS matters** — Bitbucket diffs help the AI understand implementation details not visible in the DOM.
5. **`networkidle` is unreliable** — Modern SPAs never reach network idle. Use `load` + settle delay.
6. **API token limits vary wildly** — GitHub Models API has 8K input limit; Copilot API has 200K+. Choose the right endpoint.
