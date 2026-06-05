import customtkinter as ctk
from qbot.ui.styles import COLORS, FONTS
from qbot.settings import load_settings, save_settings, get_settings_path
from qbot.config import config
from qbot.test_runner import find_chrome

GITHUB_MODELS = [
    "gpt-4o",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5-chat",
    "o4-mini",
    "o3-mini",
    "Codestral-2501",
    "mistral-small-2503",
    "mistral-medium-2505",
    "Meta-Llama-3.1-405B-Instruct",
    "Llama-3.3-70B-Instruct",
    "Llama-4-Scout-17B-16E-Instruct",
    "DeepSeek-R1-0528",
]


class SettingsDialog(ctk.CTkToplevel):
    """Settings window for configuring GitHub Copilot and app preferences."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("QBot Settings")
        self.geometry("540x620")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - 540) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - 620) // 2
        self.geometry(f"+{px}+{py}")

        self.settings = load_settings()
        self._build_ui()

    def _build_ui(self):
        ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=1, corner_radius=0).pack(fill="x")

        scroll = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_dark"])
        scroll.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(scroll, text="Settings", font=FONTS["title"],
                     text_color=COLORS["text"]).pack(pady=(0, 12), anchor="w")

        # --- GitHub Copilot ---
        self._section(scroll, "GitHub Copilot")

        ctk.CTkLabel(
            scroll, font=FONTS["small"], text_color=COLORS["text_dim"],
            wraplength=470, justify="left",
            text=(
                "QBot uses your GitHub Copilot subscription to generate tests.\n"
                "You need a Personal Access Token with 'copilot' scope.\n\n"
                "How to get your token:\n"
                "  1. Go to github.com/settings/tokens\n"
                "  2. Click 'Generate new token (classic)'\n"
                "  3. Check the 'copilot' scope\n"
                "  4. Copy the token and paste it below"
            ),
        ).pack(padx=20, pady=(4, 10), anchor="w")

        self.github_token = self._entry_row(scroll, "Token", self.settings.get("github_token", ""), show="*")

        # Model dropdown
        model_row = ctk.CTkFrame(scroll, fg_color="transparent")
        model_row.pack(fill="x", padx=20, pady=(8, 2))
        ctk.CTkLabel(model_row, text="Model", font=FONTS["body"],
                     text_color=COLORS["text"], width=80, anchor="w").pack(side="left")
        self.model_var = ctk.StringVar(value=self.settings.get("github_model", "claude-sonnet-4-20250514"))
        self.model_dropdown = ctk.CTkOptionMenu(
            model_row,
            values=GITHUB_MODELS,
            variable=self.model_var,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["accent"],
            text_color=COLORS["text"],
            width=320,
            height=36,
        )
        self.model_dropdown.pack(side="left", fill="x", expand=True)

        # --- Browser ---
        self._section(scroll, "Browser")
        chrome = find_chrome()
        chrome_text = f"Google Chrome found:\n   {chrome}" if chrome else (
            "Google Chrome NOT found.\n"
            "Install from https://google.com/chrome\n"
            "Playwright will fall back to bundled Chromium."
        )
        chrome_color = COLORS["success"] if chrome else COLORS["error"]
        ctk.CTkLabel(scroll, text=chrome_text, font=FONTS["small"], text_color=chrome_color,
                     wraplength=470, justify="left").pack(padx=20, pady=(5, 10), anchor="w")

        # --- Target Application URLs ---
        self._section(scroll, "Target Application URLs")
        ctk.CTkLabel(
            scroll, font=FONTS["small"], text_color=COLORS["text_dim"],
            wraplength=470, justify="left",
            text="Add your application URLs here. They will appear in the\nTarget URL dropdown on the main screen.",
        ).pack(padx=20, pady=(4, 6), anchor="w")

        url_add_row = ctk.CTkFrame(scroll, fg_color="transparent")
        url_add_row.pack(fill="x", padx=20, pady=(0, 4))
        self.new_url_entry = ctk.CTkEntry(
            url_add_row, placeholder_text="https://your-app.com",
            height=34, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text"], corner_radius=4,
        )
        self.new_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.new_url_entry.bind("<Return>", lambda e: self._add_url())
        ctk.CTkButton(
            url_add_row, text="+ Add", width=70, height=34,
            font=FONTS["small"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], corner_radius=4,
            command=self._add_url,
        ).pack(side="left")

        self.urls_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self.urls_frame.pack(fill="x", padx=20, pady=(0, 8))
        self._url_widgets = []
        for url in self.settings.get("target_urls", []):
            self._add_url_row(url)

        # --- Save / Cancel ---
        self.status_label = ctk.CTkLabel(scroll, text="", font=FONTS["small"], text_color=COLORS["success"])
        self.status_label.pack(pady=(8, 0))

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 5))

        ctk.CTkButton(
            btn_row, text="Save", width=140, height=40,
            font=FONTS["body_bold"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], corner_radius=4,
            command=self._save,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="Cancel", width=100, height=40,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
            hover_color=COLORS["btn_neutral"], corner_radius=4,
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkLabel(
            scroll, text=f"Config: {get_settings_path()}",
            font=FONTS["small"], text_color=COLORS["text_dim"], wraplength=490,
        ).pack(pady=(12, 0), anchor="w")

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text.upper(), font=FONTS["small"],
                     text_color=COLORS["text_dim"]).pack(padx=5, pady=(15, 6), anchor="w")

    def _entry_row(self, parent, label, value, show=None) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=2)
        ctk.CTkLabel(row, text=label, font=FONTS["body"], text_color=COLORS["text"],
                     width=80, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(
            row, height=36, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border_bright"],
            text_color=COLORS["text"], corner_radius=7,
        )
        if show:
            entry.configure(show=show)
        entry.pack(side="left", fill="x", expand=True)
        if value:
            entry.insert(0, value)
        return entry

    def _save(self):
        self.settings["ai_provider"] = "github"
        self.settings["github_token"] = self.github_token.get().strip()
        self.settings["github_model"] = self.model_var.get()
        self.settings["target_urls"] = [w["url"] for w in self._url_widgets]

        save_settings(self.settings)

        config.ai_provider = "github"
        config.github_token = self.settings["github_token"]
        config.github_model = self.settings["github_model"]

        self.status_label.configure(text="Saved!")
        self.after(1200, self.destroy)

    def _add_url(self):
        url = self.new_url_entry.get().strip()
        if not url:
            return
        # Auto-add https:// if missing
        if not url.startswith("http"):
            url = "https://" + url
        # Avoid duplicates
        existing = [w["url"] for w in self._url_widgets]
        if url in existing:
            return
        self._add_url_row(url)
        self.new_url_entry.delete(0, "end")

    def _add_url_row(self, url: str):
        row = ctk.CTkFrame(self.urls_frame, fg_color=COLORS["bg_input"], corner_radius=4, height=32)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=url, font=FONTS["small"],
                     text_color=COLORS["text"], anchor="w").pack(side="left", padx=8, fill="x", expand=True)
        entry = {"url": url, "row": row}
        ctk.CTkButton(
            row, text="×", width=28, height=24,
            font=FONTS["small"], fg_color="transparent",
            hover_color=COLORS["error"], text_color=COLORS["text_dim"],
            corner_radius=4,
            command=lambda e=entry: self._remove_url(e),
        ).pack(side="right", padx=4)
        self._url_widgets.append(entry)

    def _remove_url(self, entry):
        entry["row"].destroy()
        self._url_widgets.remove(entry)
