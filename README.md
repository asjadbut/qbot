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
