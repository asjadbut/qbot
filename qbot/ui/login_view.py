import os
import customtkinter as ctk
from PIL import Image
from qbot.ui.styles import COLORS, FONTS
from qbot.config import config
from qbot.settings import load_settings, save_settings

_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "qbot_logo.png",
)


class LoginView(ctk.CTkFrame):
    """Jira login screen — Cloud or Server/Data Center."""

    def __init__(self, parent, on_login_success, on_settings):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.on_login_success = on_login_success
        self.on_settings = on_settings
        self._build_ui()
        self._load_saved()

    def _build_ui(self):
        # VS Code–style title bar strip
        stripe = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=35, corner_radius=0)
        stripe.pack(fill="x", side="top")
        stripe.pack_propagate(False)
        stripe_row = ctk.CTkFrame(stripe, fg_color="transparent")
        stripe_row.pack(side="left", padx=8)
        if os.path.exists(_LOGO_PATH):
            small_logo = ctk.CTkImage(light_image=Image.open(_LOGO_PATH),
                                      dark_image=Image.open(_LOGO_PATH),
                                      size=(18, 18))
            ctk.CTkLabel(stripe_row, image=small_logo, text="").pack(side="left", padx=(0, 4))
        ctk.CTkLabel(stripe_row, text="QBot  —  AI Test Automation",
                     font=FONTS["small"], text_color=COLORS["text_dim"]).pack(side="left")

        # Center container
        center = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=8,
                              border_color=COLORS["border"], border_width=1)
        center.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.42)

        # Logo
        if os.path.exists(_LOGO_PATH):
            logo_img = ctk.CTkImage(light_image=Image.open(_LOGO_PATH),
                                    dark_image=Image.open(_LOGO_PATH),
                                    size=(160, 160))
            ctk.CTkLabel(center, image=logo_img, text="").pack(pady=(28, 0))
        else:
            ctk.CTkLabel(center, text="QBot", font=FONTS["title"],
                         text_color=COLORS["text"]).pack(pady=(28, 0))

        ctk.CTkLabel(center, text="AI-Powered Test Automation",
                     font=FONTS["body"], text_color=COLORS["accent"]).pack(pady=(6, 4))


        # Divider
        ctk.CTkFrame(center, fg_color=COLORS["border"], height=1).pack(fill="x", padx=30, pady=(0, 18))

        # Jira URL
        self._field_label(center, "Jira URL")
        self.url_entry = self._entry(center, "https://yoursite.atlassian.net")
        self._hint(center, "Cloud: yoursite.atlassian.net  |  Server: https://jira.company.com")

        # Username / Email
        self._field_label(center, "Username / Email")
        self.user_entry = self._entry(center, "you@company.com")

        # Password / API Token
        self._field_label(center, "Password / API Token")
        self.pass_entry = self._entry(center, "••••••••", show="•")
        self._hint(center, "Jira Cloud: use an API Token from id.atlassian.com → Security")

        # Remember me
        self.remember_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            center, text="Remember credentials", variable=self.remember_var,
            font=FONTS["body"], text_color=COLORS["text"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            border_color=COLORS["border_bright"], checkmark_color="#fff",
        ).pack(padx=35, pady=(10, 4), anchor="w")

        # Status / error label
        self.status_label = ctk.CTkLabel(
            center, text="", font=FONTS["small"], text_color=COLORS["text_dim"],
            wraplength=360, justify="left",
        )
        self.status_label.pack(padx=35, pady=(6, 0), anchor="w")

        # Login button
        self.login_btn = ctk.CTkButton(
            center, text="Connect to Jira", width=0, height=44,
            font=FONTS["body_bold"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._handle_login,
        )
        self.login_btn.pack(fill="x", padx=35, pady=(14, 28))

        self.pass_entry.bind("<Return>", lambda e: self._handle_login())

    def _field_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=FONTS["body_bold"], text_color=COLORS["text"]).pack(
            padx=35, anchor="w", pady=(0, 2)
        )

    def _entry(self, parent, placeholder, show=None) -> ctk.CTkEntry:
        e = ctk.CTkEntry(
            parent, placeholder_text=placeholder, height=40, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border_bright"],
            text_color=COLORS["text"], placeholder_text_color=COLORS["text_dim"],
            corner_radius=8,
        )
        if show:
            e.configure(show=show)
        e.pack(fill="x", padx=35, pady=(0, 8))
        return e

    def _hint(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=FONTS["small"], text_color=COLORS["text_dim"],
                     wraplength=360, justify="left").pack(padx=35, anchor="w", pady=(0, 10))

    def _load_saved(self):
        s = load_settings()
        if s.get("jira_url"):
            self.url_entry.insert(0, s["jira_url"])
        if s.get("jira_username"):
            self.user_entry.insert(0, s["jira_username"])
        if s.get("remember_jira"):
            self.remember_var.set(True)
            if s.get("jira_password"):
                self.pass_entry.insert(0, s["jira_password"])

    def _handle_login(self):
        url = self.url_entry.get().strip()
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not url:
            self._set_status("Please enter the Jira URL.", error=True)
            return
        if not username:
            self._set_status("Please enter your username or email.", error=True)
            return
        if not password:
            self._set_status("Please enter your password or API token.", error=True)
            return

        # Normalize URL for display
        display_url = url if url.startswith("http") else "https://" + url
        self.login_btn.configure(state="disabled", text="Connecting…")
        self._set_status(f"Connecting to {display_url} …", error=False)

        config.jira_url = url
        config.jira_username = username
        config.jira_password = password

        s = load_settings()
        s["jira_url"] = url
        s["jira_username"] = username
        s["remember_jira"] = self.remember_var.get()
        if self.remember_var.get():
            s["jira_password"] = password
        else:
            s.pop("jira_password", None)
        save_settings(s)

        import threading

        def do_login():
            try:
                from qbot.jira_client import JiraClient
                client = JiraClient()
                client.login(url, username, password)
                self.after(0, lambda: self._login_ok(client))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: self._login_fail(msg))

        threading.Thread(target=do_login, daemon=True).start()

    def _set_status(self, msg: str, error: bool):
        color = COLORS["error"] if error else COLORS["accent2"]
        self.status_label.configure(text=msg, text_color=color)
        self.update()

    def _login_ok(self, client):
        self.login_btn.configure(state="normal", text="Connect to Jira")
        self._set_status("✅ Connected!", error=False)
        self.on_login_success(client)

    def _login_fail(self, error_msg):
        self.login_btn.configure(state="normal", text="Connect to Jira")
        self._set_status(error_msg, error=True)


    def _build_ui(self):
        # Center container
        center = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=16, width=450)
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Logo
        if os.path.exists(_LOGO_PATH):
            logo_img = ctk.CTkImage(light_image=Image.open(_LOGO_PATH),
                                    dark_image=Image.open(_LOGO_PATH),
                                    size=(160, 160))
            ctk.CTkLabel(center, image=logo_img, text="").pack(pady=(28, 6))
        ctk.CTkLabel(center, text="AI-Powered Test Automation",
                     font=FONTS["body"], text_color=COLORS["text_dim"]).pack(pady=(0, 20))

        # Jira URL
        ctk.CTkLabel(center, text="Jira Server URL", font=FONTS["body_bold"], text_color=COLORS["text"]).pack(
            padx=40, anchor="w"
        )
        self.url_entry = ctk.CTkEntry(
            center,
            placeholder_text="https://jira.yourcompany.com",
            width=370,
            height=40,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.url_entry.pack(padx=40, pady=(5, 15))

        # Username
        ctk.CTkLabel(center, text="Username", font=FONTS["body_bold"], text_color=COLORS["text"]).pack(
            padx=40, anchor="w"
        )
        self.user_entry = ctk.CTkEntry(
            center,
            placeholder_text="your.username",
            width=370,
            height=40,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.user_entry.pack(padx=40, pady=(5, 15))

        # Password / PAT
        ctk.CTkLabel(center, text="Password / Personal Access Token", font=FONTS["body_bold"], text_color=COLORS["text"]).pack(
            padx=40, anchor="w"
        )
        self.pass_entry = ctk.CTkEntry(
            center,
            placeholder_text="••••••••",
            show="•",
            width=370,
            height=40,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.pass_entry.pack(padx=40, pady=(5, 10))

        # Remember me checkbox
        self.remember_var = ctk.BooleanVar(value=False)
        self.remember_cb = ctk.CTkCheckBox(
            center, text="Remember credentials", variable=self.remember_var,
            font=FONTS["body"], text_color=COLORS["text"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        self.remember_cb.pack(padx=40, pady=(0, 10), anchor="w")

        # Error label
        self.error_label = ctk.CTkLabel(
            center, text="", font=FONTS["small"], text_color=COLORS["error"], wraplength=350
        )
        self.error_label.pack(padx=40)

        # Login button
        self.login_btn = ctk.CTkButton(
            center,
            text="Connect to Jira",
            width=370,
            height=45,
            font=FONTS["body_bold"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["btn_text"],
            command=self._handle_login,
        )
        self.login_btn.pack(padx=40, pady=(10, 30))

        # Bind Enter key
        self.pass_entry.bind("<Return>", lambda e: self._handle_login())

    def _load_saved(self):
        """Pre-fill fields from saved settings."""
        s = load_settings()
        if s.get("jira_url"):
            self.url_entry.insert(0, s["jira_url"])
        if s.get("jira_username"):
            self.user_entry.insert(0, s["jira_username"])
        if s.get("remember_jira"):
            self.remember_var.set(True)
            if s.get("jira_password"):
                self.pass_entry.insert(0, s["jira_password"])

    def _handle_login(self):
        url = self.url_entry.get().strip()
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not url or not username or not password:
            self.error_label.configure(text="All fields are required.")
            return

        self.login_btn.configure(state="disabled", text="Connecting...")
        self.error_label.configure(text="")
        self.update()

        # Store in config
        config.jira_url = url
        config.jira_username = username
        config.jira_password = password

        # Save settings
        s = load_settings()
        s["jira_url"] = url
        s["jira_username"] = username
        s["remember_jira"] = self.remember_var.get()
        if self.remember_var.get():
            s["jira_password"] = password
        else:
            s.pop("jira_password", None)
        save_settings(s)

        import threading

        def do_login():
            try:
                from qbot.jira_client import JiraClient
                client = JiraClient()
                client.login(url, username, password)
                self.after(0, lambda: self._login_ok(client))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: self._login_fail(msg))

        threading.Thread(target=do_login, daemon=True).start()

    def _login_ok(self, client):
        self.login_btn.configure(state="normal", text="Connect to Jira")
        self.on_login_success(client)

    def _login_fail(self, error_msg):
        self.login_btn.configure(state="normal", text="Connect to Jira")
        self.error_label.configure(text=error_msg)
