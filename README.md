# QBot — AI-Powered Test Automation from Jira

A Windows desktop app that generates and runs Playwright tests from Jira tickets using AI.

## How It Works

```
Jira Ticket → Crawl Target Pages → AI Generates Tests → Playwright Executes → Results
```

1. **Fetch** a Jira ticket (Cloud or Server/DC)
2. **Crawl** the target app pages mentioned in the ticket — captures real DOM (buttons, inputs, links, selectors)
3. **AI generates** Playwright tests using the actual page structure
4. **Playwright executes** the tests in Google Chrome with saved auth state
5. **Results** displayed with pass/fail per test and raw pytest output

---

## Quick Start

### Prerequisites

- Python 3.12+
- Google Chrome
- GitHub Copilot token (PAT with `copilot` scope)

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

### GitHub Copilot Token

QBot uses GitHub Models API via your Copilot subscription.

1. Go to https://github.com/settings/tokens
2. **Generate new token (classic)** → check the `copilot` scope
3. Paste the token in QBot **Settings** (gear icon)

### Available AI Models

| Model | Notes |
|-------|-------|
| `gpt-4o` | Default, good all-rounder |
| `gpt-4.1` / `gpt-4.1-mini` | Latest GPT |
| `gpt-4o-mini` | Fast, lightweight |
| `gpt-5` / `gpt-5-mini` / `gpt-5-nano` | Newest generation |
| `o4-mini` / `o3-mini` | Reasoning models |
| `Codestral-2501` | Mistral code model |
| `Meta-Llama-3.1-405B-Instruct` | Large open model |
| `DeepSeek-R1-0528` | Reasoning model |

Select a model from the dropdown in Step 3 of the ticket view.

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

### AI Test Generation

- Sends ticket text + real page context to the selected AI model
- Generated tests use actual selectors from the crawled pages
- Strips AI-generated fixture redefinitions (AST-based) to avoid conflicts with conftest
- Validates output contains `def test_` before proceeding

### Test Execution

- Runs via `pytest` with `-v --tb=short -p no:playwright`
- Reuses auth state from crawl step (usually no second login needed)
- Each test gets a fresh browser tab in the shared authenticated context
- Results parsed from pytest output: pass/fail counts + individual test names
- Raw pytest output shown in Test Results tab for debugging failures

### Replay

After pipeline completes, click **▶ Replay Tests** to re-run without regenerating.

---

## Browser

QBot uses **Google Chrome** with anti-detection flags. If Chrome is not found, falls back to Playwright's bundled Chromium.

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
  ai_generator.py     # AI prompt + API calls (GitHub Models)
  page_crawler.py     # Playwright crawler, URL extraction, DOM snapshots
  test_runner.py      # pytest execution, conftest generation, result parsing
  jira_client.py      # Jira Cloud/Server ticket fetching
  ui/
    app.py            # Main window, view transitions
    login_view.py     # Jira login screen
    ticket_view.py    # Ticket input, URL/model selection
    runner_view.py    # Pipeline execution, live log, results display
    settings_dialog.py # Settings modal
    styles.py         # VS Code Dark color palette, fonts
```

---

## Development History

QBot was built and iteratively improved in a single AI-assisted session on June 4–5, 2026, using GitHub Copilot (Claude Opus 4) as a pair-programming partner. Every feature, bug fix, and design decision below was driven by real-time user testing and feedback.

### Phase 1: Initial Build (June 4, 6:03 PM)

**Prompt:** *"Build a Windows desktop app: Jira → AI → Playwright test automation"*

The AI asked three clarifying questions:
- Which AI provider? → **Both (OpenAI + Anthropic), configurable**
- Jira Cloud or Server? → **Jira Server/Data Center**
- Project location? → `c:\Users\butttasj\Documents\Tools\qbot`

**Created in ~7 minutes (13 files):**
- `main.py` — entry point
- `qbot/config.py` — dataclass with env-based configuration
- `qbot/jira_client.py` — Jira REST API integration (auth, ticket fetching, AC extraction)
- `qbot/ai_generator.py` — OpenAI + Anthropic test generation with system prompt
- `qbot/test_runner.py` — pytest execution, result parsing
- `qbot/ui/` — CustomTkinter UI: login → ticket → runner views
- `qbot/ui/styles.py` — dark theme colors and fonts
- `.env.example` — API key template
- `requirements.txt`, `README.md`

**Original pipeline:** AI generates → Playwright runs → AI reviews coverage → AI generates missing → Playwright re-runs (7 steps)

### Phase 2: Settings & Persistence (6:18 PM)

**Prompt:** *"for now i will be using grok as it is free and app should let the user configure these configuration through ui and save them also user should not have to login into jira every time, option should be there to remember them, also can we generate exe file"*

**Changes:**
- Created `qbot/settings.py` — JSON persistence to `%APPDATA%\QBot\settings.json`
- Created `qbot/ui/settings_dialog.py` — modal UI for configuring AI provider, API keys, models
- Added "Remember credentials" checkbox on login screen
- Created `build.py` — PyInstaller one-file build script → `dist/QBot.exe` (~80 MB)
- Switched default AI provider from OpenAI to Grok (xAI)

### Phase 3: Jira Cloud Support (6:41 PM)

**Prompt:** *"so on login screen i provided it jira server url=constellation1.atlassian.net my login email and password and click login it says connecting from a long time no error no message"*

**Root cause:** Jira Cloud uses a different auth flow than Server. The code had no timeout and no Cloud detection.

**Fixes:**
- Added `_normalise_url()` — auto-prepends `https://`, strips trailing slashes
- Added `_is_cloud()` — detects `.atlassian.net` domains
- Cloud uses email + API token auth; Server uses username + password/PAT
- Added 15-second timeout on JIRA client connection
- Better error messages on login failure

### Phase 4: VS Code Dark Theme (7:07 PM)

**Prompt:** *"i want the theme of this app to look like similar to vs code dark 2026 theme"*

**Changes:**
- Complete color palette overhaul in `styles.py`:
  - Backgrounds: `#1e1e1e` (editor), `#252526` (sidebar), `#3c3c3c` (input)
  - Accent: `#007acc` (VS Code blue)
  - Status: green/yellow/red matching VS Code
  - Syntax token colors for badges
- Redesigned ticket view with VS Code-style layout:
  - Title bar with app name
  - Activity bar (left strip with icons)
  - Step progress bar (1 → 2 → 3 → 4)
  - Two-column layout: config panels left, ticket preview right

### Phase 5: UI Layout Fixes (7:22 PM)

**Prompt:** *"as soon as i click fetch ticket the test action button disappears from the frame, maybe its position takes it out of the frame also color on fetch ticket button and connected to jira is not looking good"*

**Fixes:**
- Pinned Step 4 (Run Tests) to bottom of right column using `pack(side="bottom")` before the expanding preview card
- Changed fetch button to amber (`#e8a020`) for warmth
- Added Jira connected icon (`🔗`) in title bar
- Added settings gear icon (`⚙`) in activity bar

### Phase 6: Groq Integration Fix (7:33 PM)

**Prompt:** *"Generation failed: Error code: 400 - Model not found: qwen3-32b"*

**Root cause:** The code was calling Grok (xAI) API at `api.x.ai/v1` but user wanted Groq (different company). Model `qwen3-32b` doesn't exist on xAI.

**Fixes:**
- Changed base URL from `api.x.ai/v1` to `api.groq.com/openai/v1`
- Updated default model to `llama-3.3-70b-versatile`
- Renamed all `grok_*` config keys to `groq_*`
- Updated settings dialog labels

### Phase 7: Conftest & Chrome (7:54 PM → 8:24 PM)

**Prompt:** *"Settings popup still says grok xai and default model is grok-3"*
**Then:** *"ImportError while loading conftest... module 'playwright.sync_api' has no attribute 'sync_playwright'"*

**Fixes:**
- Cleaned duplicate class definitions in settings_dialog.py
- Fixed conftest.py generation — was importing from wrong playwright module
- Added Google Chrome detection (`find_chrome()`) — searches standard Windows install paths
- Added anti-detection flags: spoofed `navigator.webdriver`, custom user agent, disabled automation indicators
- Added stealth init script injected into every page

### Phase 8: Browser Instance Management (8:40 PM → 9:04 PM)

**Prompt:** *"it still kept opening different instances... let's make this app simple and remove the AI Reviews Coverage and AI Generates Missing Tests steps"*
**Then:** *"still facing the same issue after successful login nothing happened and a new instance of google was opened again"*

**Root cause:** `pytest-playwright` was managing its own browser, conflicting with QBot's browser. Multiple browser instances spawned.

**Fixes:**
- Simplified pipeline from 7 steps to 4: Crawl → Generate → Execute → Report
- Added `-p no:playwright` to disable pytest-playwright's browser management
- QBot manages browser directly via `sync_playwright()` in conftest.py
- Single browser instance with session-scoped fixture `_pw_session`
- Each test gets a fresh tab via `page` fixture

### Phase 9: Page Crawler (9:11 PM → 9:50 PM)

**Prompt:** *"so i ran the app instance opened up never gave me the chance to log in and tests ran and results produced"*
**Then:** *"this time it opened once, was able to log in but i can't understand the result"*

**Root cause:** AI was generating tests without seeing the actual page. Tests were hallucinated.

**Major new feature — `page_crawler.py`:**
- Opens Chrome, navigates to URLs from the Jira ticket
- Detects login pages → waits up to 5 minutes for manual login
- Saves auth state (`auth_state.json`) for reuse during test execution
- Captures DOM snapshots: headings, buttons, inputs, links, forms, visible text
- Extracts URLs from ticket text using regex
- Passes real page context to AI → tests use actual selectors

### Phase 10: GitHub Copilot Integration (9:36 PM → 9:56 PM)

**Prompt:** *"can i use github copilot in vs code to achieve the same functionality so the agent can have the context of the actual web page?"*
**Then:** *"my org has provided me with github copilot subscription can i use it for ai generates tests?"*
**Then:** *"lets only use github copilot in the app to keep things simple"*

**Major simplification:**
- Removed direct OpenAI and Anthropic as primary providers
- Added GitHub Models API (`https://models.inference.ai.azure.com`) using OpenAI SDK
- Uses GitHub PAT with `copilot` scope for authentication
- Settings UI simplified to just GitHub token + model dropdown
- Added 17 models: GPT-4o, GPT-4.1, GPT-5, o4-mini, Codestral, Llama, DeepSeek, etc.
- Special handling for reasoning models (`max_completion_tokens` vs `max_tokens`, no `temperature`)

### Phase 11: Network & Crawl Reliability (10:21 PM → 11:05 PM)

**Prompt:** *"it never went past step 2"* (multiple variations over ~45 minutes)

**Issues discovered through repeated testing:**
1. `networkidle` timeout — pages with persistent connections hang forever
2. Malformed URLs — ticket text with `|` and `]` corrupted URLs
3. DNS failures — transient network errors crashed the pipeline
4. Duplicate pages — redirects caused the same page to be crawled twice

**Fixes:**
- Changed `wait_until="networkidle"` → `wait_until="load"` + 2-second settle
- Added `_clean_url()` — strips `|`, `]`, `)` from extracted URLs
- Added 3-attempt retry with exponential backoff for transient errors
- Added URL deduplication after redirect resolution
- Added `requested_url` field to `PageSnapshot` for redirect tracking

### Phase 12: Python 3.14 Compatibility (11:05 PM)

**Prompt:** *"Exception in Tkinter callback... NameError: name 'e' is not defined"*

**Root cause:** Python 3.14 breaking change — `except Exception as e:` deletes `e` after the block exits. Lambda closures that captured `e` broke.

**Fix:** All `except Exception as e:` handlers now use `err_msg = str(e)` before the lambda:
```python
except Exception as e:
    err_msg = str(e)  # capture BEFORE block exits
    self.after(0, lambda msg=err_msg: self._log(f"Error: {msg}"))
```
Applied across `runner_view.py`, `login_view.py`.

### Phase 13: Test Results Display (11:13 PM → 12:02 AM)

**Prompt:** *"test results section needs improvement... show passed and failed test cases along with the playwright test name thats it less technical details"*

**Changes:**
- Added clean pass/fail summary with `✓` and `✗` icons
- Test names formatted from `test_some_feature` → `Some Feature`
- Stats panel on left sidebar: Passed/Failed/Skipped/Total counts
- Added Replay button (`▶ Replay Tests`) to re-run without regenerating
- Added Cancel button (`■ Stop`) with proper pipeline cancellation

### Phase 14: Settings Refresh & Test Execution (12:34 AM → 12:48 AM)

**Prompt:** *"changes saved in the settings are reflected when user closes the application and then opens it again but changes should be reflected right away... also playwright tests are not getting executed"*

**Two bugs:**
1. Settings dialog didn't refresh the ticket view after saving
2. Conftest still used `networkidle` (only crawler was fixed, not conftest)

**Fixes:**
- `_open_settings()` now uses `wait_window(dialog)` → rebuilds ticket view after dialog closes
- Changed conftest `wait_until="networkidle"` → `wait_until="load"`
- Added raw pytest output to Test Results tab for debugging

### Phase 15: Parser Rewrite (12:58 AM)

**Prompt:** *"ALL TESTS PASSED / 1 passed | 0 failed | 1 total... ✗ FAILED: TestRosterHistoryAccess (×5)"*

**Three parser bugs:**
1. Summary line `=================== 5 failed, 1 passed ===================` — the `=` padding broke `split()[0]`
2. `split("::")[1]` grabbed class name instead of test method name
3. `-v` and `-q` flags conflicted, suppressing verbose PASSED lines

**Fixes:**
- Rewrote `_parse_results()` with regex: `r'^=+\s(.+?)\s=+$'` strips `=` borders
- Test name extraction uses `split("::")[-1]` (last segment = method name)
- Removed `-q` flag, kept `-v` for verbose output
- Added deduplication (verbose line + summary both match same test)

### Phase 16: URL Variant Recognition (1:15 AM)

**Prompt:** *"why 3 4 tests failed when they should pass"*

**Root cause:** Jira ticket contained `https://my.paradym.com/account/uservoicelayout.aspx` (production URL). The crawler didn't recognize `my.paradym.com` as a variant of `my-dev.paradym.com`, so the path became `https://my-dev.paradym.com/my.paradym.com/account/...` → 404.

**Fix:**
- Added domain-variant matching in `extract_urls_from_text()`
- Strips common env prefixes: `my`, `my-dev`, `staging`, `dev`, `qa`, `uat`, etc.
- Production URLs automatically rewritten to target dev host
- Added path sanitization — skips paths containing hostnames (e.g. `/my.paradym.com/...`)

### Phase 17: AI Prompt Engineering (1:24 AM → 1:28 AM)

**Prompt:** *"6 passed | 2 failed — test_preview_buttons: assert count() == 17 but actual is 20"*
**Then:** *"goal is not to correct text but to improve the prompt by learning from this"*

**AI prompt improvements:**
- Added `ELEMENT COUNT & CONTENT ASSERTIONS` section with GOOD/BAD examples:
  - `GOOD: assert count() >= 7` vs `BAD: assert count() == 17`
  - `GOOD: expect(locator("text=X").first).to_be_visible()` vs `BAD: locator("text=INCLUDE").locator("xpath=...")`
- Banned `.all_text_contents()` exact-match assertions
- Banned complex xpath locator chains
- Added rule: don't assume UI patterns (modals, dialogs) not visible in DOM context

### Phase 18: Polish (1:37 AM)

**Prompt:** *"change color of fetch button, done button is always disabled fix that, create gitignore"*

**Final touches:**
- Fetch button: amber → VS Code blue (`#007acc`) with white text
- Done button: stays enabled after pipeline completes, shows green `✔ Done`, clicks back to ticket view
- Created `.gitignore` with Python, IDE, build, and generated test exclusions

---

### Key Lessons Learned

1. **Real page context eliminates hallucination** — The single biggest quality improvement was adding the page crawler. Without real DOM context, AI generates plausible-looking but wrong selectors.

2. **`networkidle` is unreliable** — Modern SPAs with persistent WebSocket connections, analytics pings, or long-polling never reach "network idle". Use `load` + a settle delay.

3. **Python 3.14 breaks lambda closures** — `except Exception as e:` now deletes `e` after the block. Any lambda or callback capturing `e` must bind eagerly.

4. **Concrete examples > abstract rules** — Adding `GOOD:` / `BAD:` code examples to the AI prompt was far more effective than abstract instructions like "don't use exact counts."

5. **Domain variants in tickets** — Jira tickets commonly reference production URLs while testing is done on dev/staging. URL extraction must handle `my.paradym.com` → `my-dev.paradym.com` rewrites.

6. **Parser robustness** — pytest output format changes between `-v`, `-q`, and combinations. The `===` border padding breaks naive string splitting. Use regex.
