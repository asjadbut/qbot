import threading
import webbrowser
import customtkinter as ctk
from qbot.ui.styles import COLORS, FONTS, patch_dropdown_arrow
from qbot.settings import load_settings, save_settings, get_settings_path
from qbot.config import config
from qbot.test_runner import find_chrome
from qbot import copilot_auth
from qbot.profiles import load_profiles, DEFAULT_PROFILE_ID
from qbot.ui.profiles_dialog import ProfilesDialog

GITHUB_MODELS = [
    # Claude (via Copilot API) — 4.5 series only; 4.6/4.7 are not
    # consistently available on the Copilot route
    "claude-sonnet-4.5",
    "claude-opus-4.5",
    "claude-haiku-4.5",
    # GPT (via Copilot API)
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.2",
    "gpt-5-mini",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4o-mini",
    # Gemini (via Copilot API)
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
]


class SettingsDialog(ctk.CTkToplevel):
    """Settings window — two-column layout for AI + integrations."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("QBot Settings")
        self.geometry("820x720")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = (sw - 820) // 2
        py = (sh - 720) // 2
        self.geometry(f"820x720+{px}+{py}")

        self.settings = load_settings()
        self.saved = False
        self._build_ui()

    def _build_ui(self):
        # Title bar
        titlebar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=40, corner_radius=0)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        ctk.CTkLabel(titlebar, text="  \u2699  Settings", font=FONTS["body_bold"],
                     text_color=COLORS["text"]).pack(side="left", padx=10)

        # Two-column container
        columns = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        columns.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        # ── LEFT COLUMN: AI & App ──
        left = ctk.CTkFrame(
            columns, fg_color=COLORS["bg_dark"], corner_radius=0,
            border_width=0,
        )
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # ── GitHub Copilot Card ──
        copilot_card = ctk.CTkFrame(
            left, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1,
        )
        copilot_card.pack(fill="x", pady=(0, 8))

        self._section(copilot_card, "GitHub Copilot")

        # Auth status + Authorize button
        auth_row = ctk.CTkFrame(copilot_card, fg_color="transparent")
        auth_row.pack(fill="x", padx=12, pady=(2, 6))

        authorized = copilot_auth.is_authorized()
        status_icon = "\u2713" if authorized else "\u2717"
        status_text = f"{status_icon} Authorized" if authorized else f"{status_icon} Not authorized"
        status_color = COLORS["success"] if authorized else COLORS["warning"]
        self.auth_status = ctk.CTkLabel(
            auth_row, text=status_text, font=FONTS["small"],
            text_color=status_color,
        )
        self.auth_status.pack(side="left")

        self.auth_btn = ctk.CTkButton(
            auth_row, text="Authorize Copilot" if not authorized else "Re-authorize",
            width=140, height=28, font=FONTS["small"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["btn_text"],
            corner_radius=4, command=self._start_copilot_auth,
        )
        self.auth_btn.pack(side="right")

        self._hint(copilot_card,
            "Click Authorize to sign in with GitHub.\n"
            "This grants access to Claude, GPT, and other\n"
            "models via your Copilot subscription.")

        model_row = ctk.CTkFrame(copilot_card, fg_color="transparent")
        model_row.pack(fill="x", padx=12, pady=(6, 12))
        ctk.CTkLabel(model_row, text="Model", font=FONTS["body"],
                     text_color=COLORS["text"], width=80, anchor="w").pack(side="left")
        self.model_var = ctk.StringVar(value=self.settings.get("github_model", "gpt-4o"))
        om = ctk.CTkOptionMenu(
            model_row, values=GITHUB_MODELS, variable=self.model_var,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"], dropdown_hover_color=COLORS["accent"],
            dropdown_text_color=COLORS["text"],
            text_color=COLORS["text"], height=34,
        )
        om.pack(side="left", fill="x", expand=True)
        patch_dropdown_arrow(om)

        # ── App Settings Card ──
        app_card = ctk.CTkFrame(
            left, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1,
        )
        app_card.pack(fill="x", pady=(0, 8))

        # Theme
        self._section(app_card, "Theme")
        theme_row = ctk.CTkFrame(app_card, fg_color="transparent")
        theme_row.pack(fill="x", padx=12, pady=(2, 8))
        self.theme_var = ctk.StringVar(value=self.settings.get("theme", "dark"))
        for label, val in [("Dark", "dark"), ("Light", "light")]:
            ctk.CTkRadioButton(
                theme_row, text=label, variable=self.theme_var, value=val,
                font=FONTS["body"], text_color=COLORS["text"],
                fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
            ).pack(side="left", padx=(0, 16))

        # Browser status
        self._section(app_card, "Browser")
        chrome = find_chrome()
        icon = "\u2713" if chrome else "\u2717"
        text = f"{icon} Google Chrome found" if chrome else f"{icon} Chrome not found \u2014 will use Chromium"
        color = COLORS["success"] if chrome else COLORS["warning"]
        ctk.CTkLabel(app_card, text=text, font=FONTS["small"],
                     text_color=color).pack(padx=12, pady=(2, 8), anchor="w")

        # Target URLs
        self._section(app_card, "Target Application URLs")
        self._hint(app_card, "URLs for the target app dropdown on the main screen.")

        url_row = ctk.CTkFrame(app_card, fg_color="transparent")
        url_row.pack(fill="x", padx=12, pady=(0, 4))
        self.new_url_entry = ctk.CTkEntry(
            url_row, placeholder_text="https://your-app.com",
            height=32, font=FONTS["small"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text"], corner_radius=4,
        )
        self.new_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.new_url_entry.bind("<Return>", lambda e: self._add_url())
        ctk.CTkButton(
            url_row, text="+ Add", width=56, height=32,
            font=FONTS["small"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._add_url,
        ).pack(side="left")

        self.urls_frame = ctk.CTkFrame(app_card, fg_color="transparent")
        self.urls_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._url_widgets = []
        for url in self.settings.get("target_urls", []):
            self._add_url_row(url)

        # ── RIGHT COLUMN: Integrations ──
        right = ctk.CTkFrame(
            columns, fg_color=COLORS["bg_dark"], corner_radius=0,
            border_width=0,
        )
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # ── Bitbucket Cloud Card ──
        bb_card = ctk.CTkFrame(
            right, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1,
        )
        bb_card.pack(fill="x", pady=(0, 8))

        self._section(bb_card, "Bitbucket Cloud")
        self._hint(bb_card,
            "Enrich AI context with code diffs from commits\n"
            "linked to each Jira ticket.\n\n"
            "Requires a Bitbucket API Token with scopes:\n"
            "  id.atlassian.com \u2192 Security \u2192 API tokens\n"
            "  Create API token \u2192 App: Bitbucket\n"
            "  Scope: Repositories \u2192 Read")
        self.bb_workspace = self._field(bb_card, "Workspace", self.settings.get("bitbucket_workspace", ""))
        self.bb_repo = self._field(bb_card, "Repository", self.settings.get("bitbucket_repo", ""))
        self.bb_api_token = self._field(bb_card, "API Token", self.settings.get("bitbucket_api_token", ""), show="*")

        # ── Team Profile Card ──
        profile_card = ctk.CTkFrame(
            right, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1,
        )
        profile_card.pack(fill="x", pady=(0, 8))

        self._section(profile_card, "Team Profile")
        self._hint(profile_card,
            "Pick the QA mindset and product knowledge\n"
            "used to generate tests. Each team can keep\n"
            "their own profile with style rules,\n"
            "tech-stack hints and a glossary.")

        prof_row = ctk.CTkFrame(profile_card, fg_color="transparent")
        prof_row.pack(fill="x", padx=12, pady=(2, 6))
        ctk.CTkLabel(
            prof_row, text="Active", font=FONTS["body"],
            text_color=COLORS["text"], width=80, anchor="w",
        ).pack(side="left")

        self._profile_objs = load_profiles()
        self._profile_name_to_id = {p.name: p.id for p in self._profile_objs}
        active_id = self.settings.get("active_profile", DEFAULT_PROFILE_ID) or DEFAULT_PROFILE_ID
        active_name = next(
            (p.name for p in self._profile_objs if p.id == active_id),
            self._profile_objs[0].name if self._profile_objs else "",
        )
        self.profile_var = ctk.StringVar(value=active_name)
        self.profile_menu = ctk.CTkOptionMenu(
            prof_row,
            values=[p.name for p in self._profile_objs] or ["(none)"],
            variable=self.profile_var,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"], dropdown_hover_color=COLORS["accent"],
            dropdown_text_color=COLORS["text"], text_color=COLORS["text"], height=32,
        )
        self.profile_menu.pack(side="left", fill="x", expand=True)
        patch_dropdown_arrow(self.profile_menu)

        manage_row = ctk.CTkFrame(profile_card, fg_color="transparent")
        manage_row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(
            manage_row, text="Manage Profiles…", height=30,
            font=FONTS["small"], fg_color=COLORS["btn_neutral"],
            hover_color=COLORS["btn_neutral_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._open_profiles,
        ).pack(side="left")

        # ── BOTTOM BAR: Save / Cancel ──
        bottom = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        bottom.pack(fill="x", padx=12, pady=(8, 12))

        ctk.CTkButton(
            bottom, text="Save", width=140, height=36,
            font=FONTS["body_bold"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._save,
        ).pack(side="left")

        ctk.CTkButton(
            bottom, text="Cancel", width=100, height=36,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
            hover_color=COLORS["btn_neutral"], corner_radius=4,
            command=self.destroy,
        ).pack(side="left", padx=(8, 0))

        self.status_label = ctk.CTkLabel(bottom, text="", font=FONTS["small"], text_color=COLORS["success"])
        self.status_label.pack(side="left", padx=16)

        ctk.CTkLabel(
            bottom, text=f"Config: {get_settings_path()}",
            font=("Consolas", 10), text_color=COLORS["text_dim"],
        ).pack(side="right")

    # ── Helpers ──

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text.upper(), font=FONTS["small"],
                     text_color=COLORS["text_dim"]).pack(padx=12, pady=(14, 4), anchor="w")

    def _hint(self, parent, text):
        ctk.CTkLabel(parent, font=FONTS["small"], text_color=COLORS["text_dim"],
                     wraplength=330, justify="left", text=text,
                     ).pack(padx=12, pady=(0, 6), anchor="w")

    def _field(self, parent, label, value, show=None) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row, text=label, font=FONTS["body"], text_color=COLORS["text"],
                     width=80, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(
            row, height=34, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text"], corner_radius=6,
        )
        if show:
            entry.configure(show=show)
        entry.pack(side="left", fill="x", expand=True)
        if value:
            entry.insert(0, value)
        return entry

    def _save(self):
        self.settings["ai_provider"] = "github"
        self.settings["github_model"] = self.model_var.get()
        self.settings["theme"] = self.theme_var.get()
        self.settings["target_urls"] = [w["url"] for w in self._url_widgets]
        self.settings["bitbucket_workspace"] = self.bb_workspace.get().strip()
        self.settings["bitbucket_repo"] = self.bb_repo.get().strip()
        self.settings["bitbucket_api_token"] = self.bb_api_token.get().strip()

        # Active team profile (resolve display name -> id)
        selected_name = self.profile_var.get()
        active_id = self._profile_name_to_id.get(selected_name, DEFAULT_PROFILE_ID)
        self.settings["active_profile"] = active_id

        save_settings(self.settings)

        # Apply theme
        from qbot.ui.styles import set_theme
        set_theme(self.settings["theme"])
        ctk.set_appearance_mode(self.settings["theme"])

        config.ai_provider = "github"
        config.github_model = self.settings["github_model"]
        config.bitbucket_workspace = self.settings["bitbucket_workspace"]
        config.bitbucket_repo = self.settings["bitbucket_repo"]
        config.bitbucket_api_token = self.settings["bitbucket_api_token"]
        config.active_profile = active_id

        self.saved = True
        self.status_label.configure(text="\u2713 Saved!")
        self.after(1200, self.destroy)

    def _open_profiles(self):
        """Open the profile editor; refresh the dropdown when the user saves."""
        ProfilesDialog(self, on_save=self._refresh_profiles)

    def _refresh_profiles(self):
        """Reload profiles from disk and update the dropdown after the editor closes."""
        self._profile_objs = load_profiles()
        self._profile_name_to_id = {p.name: p.id for p in self._profile_objs}
        names = [p.name for p in self._profile_objs] or ["(none)"]
        self.profile_menu.configure(values=names)
        # Keep current selection if its name still exists, otherwise fall back
        current = self.profile_var.get()
        if current not in names:
            default_name = next(
                (p.name for p in self._profile_objs if p.id == DEFAULT_PROFILE_ID),
                names[0],
            )
            self.profile_var.set(default_name)

    def _add_url(self):
        url = self.new_url_entry.get().strip()
        if not url:
            return
        if not url.startswith("http"):
            url = "https://" + url
        existing = [w["url"] for w in self._url_widgets]
        if url in existing:
            return
        self._add_url_row(url)
        self.new_url_entry.delete(0, "end")

    def _add_url_row(self, url: str):
        row = ctk.CTkFrame(self.urls_frame, fg_color=COLORS["bg_input"], corner_radius=4, height=30)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=url, font=FONTS["small"],
                     text_color=COLORS["text"], anchor="w").pack(side="left", padx=8, fill="x", expand=True)
        entry = {"url": url, "row": row}
        ctk.CTkButton(
            row, text="\u00d7", width=26, height=22,
            font=FONTS["small"], fg_color="transparent",
            hover_color=COLORS["error"], text_color=COLORS["text_dim"],
            corner_radius=4,
            command=lambda e=entry: self._remove_url(e),
        ).pack(side="right", padx=4)
        self._url_widgets.append(entry)

    def _remove_url(self, entry):
        entry["row"].destroy()
        self._url_widgets.remove(entry)

    def _start_copilot_auth(self):
        """Kick off the OAuth device flow in a background thread."""
        self.auth_btn.configure(state="disabled", text="Starting...")
        self.auth_status.configure(text="Starting device flow...", text_color=COLORS["text_dim"])

        def _run():
            try:
                flow = copilot_auth.start_device_flow()
                user_code = flow["user_code"]
                device_code = flow["device_code"]
                interval = flow.get("interval", 5)
                verify_url = flow["verification_uri"]

                # Update UI with user code
                self.after(0, lambda: self.auth_status.configure(
                    text=f"Enter code: {user_code}", text_color=COLORS["accent"]))
                self.after(0, lambda: self.auth_btn.configure(
                    state="normal", text="Waiting..."))

                # Open browser
                webbrowser.open(verify_url)

                # Poll for auth (up to 5 min)
                copilot_auth.poll_for_token(device_code, interval=interval, timeout=300)

                # Verify it works by exchanging for Copilot token
                copilot_auth.get_copilot_token()

                self.after(0, lambda: self.auth_status.configure(
                    text="\u2713 Authorized!", text_color=COLORS["success"]))
                self.after(0, lambda: self.auth_btn.configure(
                    state="normal", text="Re-authorize"))
            except Exception as e:
                err = str(e)[:80]
                self.after(0, lambda: self.auth_status.configure(
                    text=f"\u2717 {err}", text_color=COLORS["error"]))
                self.after(0, lambda: self.auth_btn.configure(
                    state="normal", text="Authorize Copilot"))

        threading.Thread(target=_run, daemon=True).start()
