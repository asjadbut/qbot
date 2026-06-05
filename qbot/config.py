import os
from dataclasses import dataclass
from qbot.settings import load_settings


@dataclass
class Config:
    # AI settings — GitHub Copilot only
    ai_provider: str = "github"
    github_token: str = ""
    github_model: str = "gpt-4o"

    # Legacy keys kept for migration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Jira settings (set at runtime after login)
    jira_url: str = ""
    jira_username: str = ""
    jira_password: str = ""  # password or PAT

    # Test output directory
    test_output_dir: str = ""

    # Target app base URL for testing
    target_base_url: str = ""

    def load_from_disk(self):
        """Load saved settings into this config object."""
        s = load_settings()
        for key, val in s.items():
            if hasattr(self, key) and val:
                setattr(self, key, val)
        if not self.test_output_dir:
            self.test_output_dir = os.path.join(os.getcwd(), "generated_tests")


config = Config()
config.load_from_disk()
