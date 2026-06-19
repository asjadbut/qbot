import os
import json
from pathlib import Path

SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", str(Path.home())), "QBot")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULTS = {
    "ai_provider": "github",
    "openai_api_key": "",
    "openai_model": "gpt-4o",
    "anthropic_api_key": "",
    "anthropic_model": "",
    "groq_api_key": "",
    "groq_model": "",
    "github_token": "",
    "github_model": "claude-sonnet-4.6",
    "jira_url": "",
    "jira_username": "",
    "jira_password": "",
    "remember_jira": False,
    "target_base_url": "",
    "target_urls": [],
    "bitbucket_workspace": "",
    "bitbucket_repo": "",
    "bitbucket_api_token": "",
    "test_output_dir": "",
    "theme": "dark",
    "active_profile": "default",
}


def _ensure_dir():
    os.makedirs(SETTINGS_DIR, exist_ok=True)


def load_settings() -> dict:
    """Load settings from disk, returning defaults for missing keys."""
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Migrate old 'grok' keys → 'groq'
            if "grok_api_key" in saved and "groq_api_key" not in saved:
                saved["groq_api_key"] = saved.pop("grok_api_key")
            if "grok_model" in saved and "groq_model" not in saved:
                saved["groq_model"] = saved.pop("grok_model")
            if saved.get("ai_provider") == "grok":
                saved["ai_provider"] = "groq"
            settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict):
    """Persist settings to disk."""
    _ensure_dir()
    # Never save password unless remember is checked
    to_save = dict(settings)
    if not to_save.get("remember_jira"):
        to_save.pop("jira_password", None)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)


def get_settings_path() -> str:
    return SETTINGS_FILE
