import os
import customtkinter as ctk
from qbot.ui.styles import COLORS, set_theme
from qbot.ui.login_view import LoginView
from qbot.ui.ticket_view import TicketView
from qbot.ui.runner_view import RunnerView
from qbot.ui.settings_dialog import SettingsDialog
from qbot.jira_client import JiraClient, TicketDetails
from qbot.settings import load_settings

# Resolve icon path (works both in dev and PyInstaller bundle)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ICO_PATH = os.path.join(_ROOT, "qbot.ico")


class QBotApp(ctk.CTk):
    """Main application window managing view transitions."""

    def __init__(self):
        super().__init__()

        # Window config
        self.title("QBot — AI-Powered Test Automation")
        self.geometry("1100x750")
        self.minsize(900, 650)

        # Apply saved theme
        saved_theme = load_settings().get("theme", "dark")
        set_theme(saved_theme)
        ctk.set_appearance_mode(saved_theme)
        ctk.set_default_color_theme("dark-blue")

        self.configure(fg_color=COLORS["bg_dark"])

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 1100) // 2
        y = max(0, (sh - 750) // 2 - 40)  # offset for taskbar
        self.geometry(f"1100x750+{x}+{y}")

        # Set window icon
        if os.path.exists(_ICO_PATH):
            self.iconbitmap(_ICO_PATH)

        # State
        self.jira_client: JiraClient = None
        self.current_view = None

        # Start with login
        self._show_login()

    def _clear_view(self):
        if self.current_view:
            self.current_view.destroy()
            self.current_view = None

    def _open_settings(self):
        dialog = SettingsDialog(self)
        self.wait_window(dialog)
        # Refresh current view only if settings were actually saved
        if getattr(dialog, 'saved', False):
            if isinstance(self.current_view, TicketView):
                self._show_ticket_view()

    def _show_login(self):
        self._clear_view()
        self.current_view = LoginView(self, on_login_success=self._on_login_success, on_settings=self._open_settings)
        self.current_view.pack(fill="both", expand=True)

    def _on_login_success(self, client: JiraClient):
        self.jira_client = client
        self._show_ticket_view()

    def _show_ticket_view(self):
        self._clear_view()
        self.current_view = TicketView(
            self,
            jira_client=self.jira_client,
            on_ticket_ready=self._on_ticket_ready,
            on_settings=self._open_settings,
        )
        self.current_view.pack(fill="both", expand=True)

    def _on_ticket_ready(self, ticket: TicketDetails, ticket_text: str):
        self._show_runner_view(ticket, ticket_text)

    def _show_runner_view(self, ticket: TicketDetails, ticket_text: str):
        self._clear_view()
        self.current_view = RunnerView(
            self,
            ticket=ticket,
            ticket_text=ticket_text,
            on_back=self._show_ticket_view,
        )
        self.current_view.pack(fill="both", expand=True)
