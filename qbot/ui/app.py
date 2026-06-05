import customtkinter as ctk
from qbot.ui.styles import COLORS
from qbot.ui.login_view import LoginView
from qbot.ui.ticket_view import TicketView
from qbot.ui.runner_view import RunnerView
from qbot.ui.settings_dialog import SettingsDialog
from qbot.jira_client import JiraClient, TicketDetails


class QBotApp(ctk.CTk):
    """Main application window managing view transitions."""

    def __init__(self):
        super().__init__()

        # Window config
        self.title("QBot — AI-Powered Test Automation")
        self.geometry("1100x750")
        self.minsize(900, 650)
        self.configure(fg_color=COLORS["bg_dark"])

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 1100) // 2
        y = (self.winfo_screenheight() - 750) // 2
        self.geometry(f"+{x}+{y}")

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
        # Refresh current view so settings changes take effect immediately
        if isinstance(self.current_view, TicketView):
            self._show_ticket_view()
        elif isinstance(self.current_view, LoginView):
            self._show_login()

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
