# QBot - AI Test Automation from Jira Tickets

A Windows desktop app that generates and executes Playwright tests from Jira tickets using GitHub Copilot AI.

## How It Works

```
Jira Ticket
    |
Crawl Target Pages (captures real DOM selectors)
    |
AI Generates Tests (using actual page structure - no hallucination)
    |
Playwright Executes (Google Chrome with anti-detection)
    |
Final Report
```

---

## Setup

### Prerequisites

- Python 3.12+
- Google Chrome (recommended)
- GitHub Copilot subscription (via your org)

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### Run

```bash
python main.py
```

Or use the pre-built **dist/QBot.exe**.

---

## Step 1: GitHub Copilot Login

QBot uses your GitHub Copilot subscription to access AI models (Claude, GPT-4o, etc.).

**How to get your token:**

1. Go to https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Give it a name (e.g. "QBot")
4. Check the **copilot** scope
5. Click **Generate token**
6. Copy the token

In QBot, open **Settings** (gear icon) and paste your token.

**Available models:**

| Model | Best for |
|-------|----------|
| `claude-sonnet-4-20250514` | Fast + accurate (default) |
| `claude-opus-4-20250514` | Most capable, slower |
| `gpt-4o` | Good all-rounder |
| `gpt-4.1` | Latest GPT |
| `o4-mini` | Fast reasoning |
| `o3` | Deep reasoning |
| `gemini-2.5-pro` | Google's best |

---

## Step 2: Jira Login

Enter your Jira credentials to fetch tickets.

| Jira type | URL format | Password field |
|-----------|-----------|----------------|
| **Jira Cloud** | `yoursite.atlassian.net` | API Token |
| **Jira Server/DC** | `https://jira.company.com` | Password or PAT |

> **Jira Cloud users:** Use an API Token, not your password.
> Generate one at: https://id.atlassian.com/manage-profile/security/api-tokens

Check **Remember credentials** to auto-fill on next launch.

---

## Step 3: Run the Pipeline

1. Enter a ticket key (e.g. `PROJ-1234`) and click **Fetch**
2. Set the **Target App URL** (the URL of the app being tested)
3. Select an **AI Model** from the dropdown
4. Click **Run Tests**

### What happens:

1. **Crawl** - Chrome opens, you log into the target app, QBot crawls the pages mentioned in the ticket and captures real DOM structure (buttons, inputs, links, selectors)
2. **Generate** - AI creates Playwright tests using the real selectors from step 1
3. **Execute** - Tests run in Chrome using saved auth state (usually no second login needed)
4. **Report** - Results shown with pass/fail for each test

---

## Browser

QBot uses **Google Chrome** with anti-detection flags:
- Custom user agent
- navigator.webdriver spoofed
- Automation detection disabled

If Chrome is not found, falls back to Playwright bundled Chromium.

Install Chrome: https://google.com/chrome

---

## Settings

Settings saved to: `%APPDATA%\QBot\settings.json`

Access via the gear icon in the app.

---

## Build exe

```bash
python build.py
```

Output: `dist/QBot.exe` (~80MB standalone)
