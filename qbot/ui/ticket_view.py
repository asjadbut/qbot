import threading
import customtkinter as ctk
from qbot.ui.styles import COLORS, FONTS, patch_dropdown_arrow
from qbot.jira_client import JiraClient, TicketDetails
from qbot.settings import load_settings
from qbot.ui.settings_dialog import GITHUB_MODELS
from qbot.config import config


class TicketView(ctk.CTkFrame):
    """Ticket input view with clear numbered step guide."""

    def __init__(self, parent, jira_client: JiraClient, on_ticket_ready, on_settings):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.jira = jira_client
        self.on_ticket_ready = on_ticket_ready
        self.on_settings = on_settings
        self.ticket: TicketDetails = None
        self._build_ui()

    # ──────────────────────────────────────────────────────────────────
    #  UI construction
    # ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # VS Code–style title bar
        titlebar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=35, corner_radius=0)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        ctk.CTkLabel(titlebar, text="  ⬡ QBot  —  Jira Test Automation",
                     font=FONTS["small"], text_color=COLORS["text_dim"]).pack(side="left", padx=8)

        # Jira connected indicator with icon
        jira_status = ctk.CTkFrame(titlebar, fg_color="transparent")
        jira_status.pack(side="right", padx=12)
        ctk.CTkLabel(jira_status, text="🔗", font=("Segoe UI", 12),
                     text_color=COLORS["accent"]).pack(side="left")
        ctk.CTkLabel(jira_status, text=" Jira Connected",
                     font=FONTS["small"], text_color=COLORS["success"]).pack(side="left")

        # Activity bar (left thin strip)
        activity = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], width=48, corner_radius=0)
        activity.pack(side="left", fill="y")
        activity.pack_propagate(False)

        # Clipboard icon
        ctk.CTkButton(
            activity, text="📋", width=48, height=48, fg_color="transparent",
            hover_color=COLORS["btn_neutral"], font=("Segoe UI", 16), text_color=COLORS["text_dim"],
            corner_radius=0,
        ).pack(pady=4)

        # Settings gear icon
        ctk.CTkButton(
            activity, text="\u2699", width=48, height=48, fg_color="transparent",
            hover_color=COLORS["btn_neutral"], font=("Segoe UI", 18), text_color=COLORS["text_dim"],
            corner_radius=0,
            command=self.on_settings,
        ).pack(pady=4)

        # Main workspace
        workspace = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        workspace.pack(side="left", fill="both", expand=True)

        # ── Step progress bar ──────────────────────────────────────────
        steps_bar = ctk.CTkFrame(workspace, fg_color=COLORS["bg_card"], height=44, corner_radius=0)
        steps_bar.pack(fill="x")
        steps_bar.pack_propagate(False)

        self._step_indicators = {}
        step_defs = [
            ("step1", "1  Fetch Ticket"),
            ("sep1", "›"),
            ("step2", "2  Set App URL"),
            ("sep2", "›"),
            ("step3", "3  Choose AI"),
            ("sep3", "›"),
            ("step4", "4  Run Tests"),
        ]
        for key, label in step_defs:
            if key.startswith("sep"):
                ctk.CTkLabel(steps_bar, text=label, font=FONTS["small"],
                             text_color=COLORS["text_dim"]).pack(side="left", padx=2)
            else:
                lbl = ctk.CTkLabel(steps_bar, text=label, font=FONTS["small"],
                                   text_color=COLORS["text_dim"],
                                   fg_color="transparent", corner_radius=4,
                                   padx=10, pady=4)
                lbl.pack(side="left", padx=2, pady=6)
                self._step_indicators[key] = lbl
        self._highlight_step("step1")

        # ── Two-column content layout ──────────────────────────────────
        cols = ctk.CTkFrame(workspace, fg_color=COLORS["bg_dark"])
        cols.pack(fill="both", expand=True, padx=0, pady=0)

        # Left column: config panels
        left = ctk.CTkFrame(cols, fg_color=COLORS["bg_dark"], width=420)
        left.pack(side="left", fill="y", padx=(16, 8), pady=16)
        left.pack_propagate(False)

        # Right column: ticket preview + run button
        right = ctk.CTkFrame(cols, fg_color=COLORS["bg_dark"])
        right.pack(side="left", fill="both", expand=True, padx=(8, 16), pady=16)

        # ── LEFT: Step 1 — Fetch Ticket ───────────────────────────────
        self._panel_header(left, "STEP 1", "Fetch Jira Ticket", "token_keyword")
        fetch_card = self._card(left)

        fetch_row = ctk.CTkFrame(fetch_card, fg_color="transparent")
        fetch_row.pack(fill="x", padx=12, pady=(10, 12))

        self.ticket_entry = ctk.CTkEntry(
            fetch_row, placeholder_text="e.g. PROJ-1234", height=38, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text"], placeholder_text_color=COLORS["text_dim"],
            corner_radius=4,
        )
        self.ticket_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ticket_entry.bind("<Return>", lambda e: self._fetch_ticket())

        self.fetch_btn = ctk.CTkButton(
            fetch_row, text="Fetch", width=80, height=38,
            font=FONTS["body_bold"], fg_color=COLORS["btn_fetch"],
            hover_color=COLORS["btn_fetch_hover"], text_color="#ffffff",
            corner_radius=4,
            command=self._fetch_ticket,
        )
        self.fetch_btn.pack(side="left")

        self.fetch_status = ctk.CTkLabel(fetch_card, text="", font=FONTS["small"],
                                         text_color=COLORS["text_dim"], wraplength=360, anchor="w")
        self.fetch_status.pack(padx=12, pady=(0, 10), fill="x")

        # ── LEFT: Step 2 — App URL ────────────────────────────────────
        self._panel_header(left, "STEP 2", "Target Application URL", "token_string")
        url_card = self._card(left)

        # Load saved URLs from settings for the dropdown
        saved_settings = load_settings()
        saved_urls = saved_settings.get("target_urls", [])
        current_url = config.target_base_url or (saved_urls[0] if saved_urls else "")
        self.url_var = ctk.StringVar(value=current_url)

        if saved_urls:
            self.url_dropdown = ctk.CTkOptionMenu(
                url_card,
                values=saved_urls,
                variable=self.url_var,
                font=FONTS["body"],
                fg_color=COLORS["bg_input"],
                button_color=COLORS["accent"],
                button_hover_color=COLORS["accent_hover"],
                dropdown_fg_color=COLORS["bg_card"],
                dropdown_hover_color=COLORS["accent"],
                dropdown_text_color=COLORS["text"],
                text_color=COLORS["text"],
                text_color_disabled=COLORS["text_dim"],
                height=38,
            )
            self.url_dropdown.pack(fill="x", padx=12, pady=(10, 4))
            patch_dropdown_arrow(self.url_dropdown)
        else:
            self.url_entry_field = ctk.CTkEntry(
                url_card, placeholder_text="https://your-app.com",
                height=38, font=FONTS["body"],
                fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                text_color=COLORS["text"], placeholder_text_color=COLORS["text_dim"],
                corner_radius=4, textvariable=self.url_var,
            )
            self.url_entry_field.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(url_card, text="Add URLs in Settings to populate this dropdown.",
                     font=FONTS["small"], text_color=COLORS["text_dim"], anchor="w").pack(
            padx=12, pady=(0, 10), fill="x")

        # ── LEFT: Step 3 — AI Model ──────────────────────────────────
        self._panel_header(left, "STEP 3", "AI Model (GitHub Copilot)", "token_fn")
        ai_card = self._card(left)

        ctk.CTkLabel(
            ai_card, text="Select model:", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=14, pady=(4, 4), anchor="w")

        github_models = GITHUB_MODELS
        self.model_var = ctk.StringVar(value=config.github_model)
        self.model_dropdown = ctk.CTkOptionMenu(
            ai_card,
            values=github_models,
            variable=self.model_var,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["accent"],
            dropdown_text_color=COLORS["text"],
            text_color=COLORS["text"],
            text_color_disabled=COLORS["text_dim"],
            width=280,
            height=36,
        )
        self.model_dropdown.pack(padx=14, pady=(0, 8), anchor="w")
        patch_dropdown_arrow(self.model_dropdown)
        ctk.CTkFrame(ai_card, height=4, fg_color="transparent").pack()

        # ── RIGHT column: pin Step 4 to BOTTOM first, then preview fills rest ──
        # Must pack bottom section BEFORE the expanding details card,
        # otherwise expand=True pushes the run button off screen.

        # ── Step 4 — pinned to bottom ─────────────────────────────────
        run_section = ctk.CTkFrame(right, fg_color=COLORS["bg_dark"])
        run_section.pack(side="bottom", fill="x", pady=(8, 0))

        run_header_row = ctk.CTkFrame(run_section, fg_color="transparent")
        run_header_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(run_header_row, text=" STEP 4 ", font=FONTS["small"],
                     text_color=COLORS["accent2"], fg_color=COLORS["bg_card"],
                     corner_radius=3, padx=4).pack(side="left")
        ctk.CTkLabel(run_header_row, text="  Start AI Test Pipeline",
                     font=FONTS["body_bold"], text_color=COLORS["text"]).pack(side="left")

        run_card = ctk.CTkFrame(run_section, fg_color=COLORS["bg_card"], corner_radius=6)
        run_card.pack(fill="x")

        run_inner = ctk.CTkFrame(run_card, fg_color="transparent")
        run_inner.pack(fill="x", padx=14, pady=12)

        self.run_hint = ctk.CTkLabel(
            run_inner,
            text="← Fetch a ticket first, then click Run.",
            font=FONTS["small"], text_color=COLORS["text_dim"],
        )
        self.run_hint.pack(side="left", padx=(0, 16))

        self.generate_btn = ctk.CTkButton(
            run_inner,
            text="▶  Run Tests",
            width=180, height=46,
            font=("Segoe UI", 14, "bold"),
            fg_color=COLORS["btn_neutral"],
            hover_color=COLORS["btn_neutral_hover"],
            text_color=COLORS["text_dim"],
            corner_radius=4,
            command=self._start_generation,
            state="disabled",
        )
        self.generate_btn.pack(side="right")

        # ── RIGHT: Ticket preview (fills remaining space) ─────────────
        self._panel_header(right, "PREVIEW", "Ticket Details", "token_comment")

        self.details_card = self._card(right, expand=True)

        self.details_placeholder = ctk.CTkLabel(
            self.details_card,
            text=(
                "Fetch a ticket to see its details here.\n\n"
                "The AI will use the summary, description,\n"
                "and acceptance criteria to write your tests."
            ),
            font=FONTS["body"], text_color=COLORS["text_dim"],
            justify="center",
        )
        self.details_placeholder.place(relx=0.5, rely=0.4, anchor="center")

        self.details_meta = ctk.CTkLabel(
            self.details_card, text="", font=FONTS["body"],
            text_color=COLORS["info"], anchor="w", wraplength=460, justify="left",
        )
        self.details_meta.pack(padx=14, pady=(10, 4), fill="x")
        self.details_meta.pack_forget()

        self.details_text = ctk.CTkTextbox(
            self.details_card, font=FONTS["mono_small"],
            fg_color=COLORS["bg_input"], text_color=COLORS["text"],
            wrap="word",
        )
        self.details_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.details_text.pack_forget()

    # ──────────────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────────────
    def _card(self, parent, expand=False) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=6)
        if expand:
            f.pack(fill="both", expand=True, pady=(0, 8))
        else:
            f.pack(fill="x", pady=(0, 8))
        return f

    def _panel_header(self, parent, badge: str, title: str, color_key: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(row, text=f" {badge} ", font=FONTS["small"],
                     text_color=COLORS[color_key],
                     fg_color=COLORS["bg_card"], corner_radius=3,
                     padx=4).pack(side="left")
        ctk.CTkLabel(row, text=f"  {title}", font=FONTS["body_bold"],
                     text_color=COLORS["text"]).pack(side="left")

    def _highlight_step(self, active_key: str):
        for key, lbl in self._step_indicators.items():
            if key == active_key:
                lbl.configure(text_color=COLORS["btn_text"],
                               fg_color=COLORS["accent"])
            else:
                lbl.configure(text_color=COLORS["text_dim"],
                               fg_color="transparent")

    # ──────────────────────────────────────────────────────────────────
    #  Logic
    # ──────────────────────────────────────────────────────────────────
    def _fetch_ticket(self):
        ticket_key = self.ticket_entry.get().strip().upper()
        if not ticket_key:
            self.fetch_status.configure(text="Enter a ticket number.", text_color=COLORS["error"])
            return

        self.fetch_btn.configure(state="disabled", text="Fetching…")
        self.fetch_status.configure(text=f"Fetching {ticket_key}…", text_color=COLORS["text_dim"])
        self.update()

        def do_fetch():
            try:
                ticket = self.jira.fetch_ticket(ticket_key)
                self.after(0, lambda: self._show_ticket(ticket))
            except Exception as e:
                self.after(0, lambda: self._fetch_fail(str(e)))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _show_ticket(self, ticket: TicketDetails):
        self.ticket = ticket
        self.fetch_btn.configure(state="normal", text="Fetch")
        self.fetch_status.configure(
            text=f"✔  {ticket.key} fetched — {ticket.issue_type} · {ticket.status}",
            text_color=COLORS["success"],
        )

        # Populate preview
        self.details_placeholder.place_forget()
        self.details_meta.configure(
            text=f"{ticket.key}  ·  {ticket.summary}\n"
                 f"Type: {ticket.issue_type}   Status: {ticket.status}   Priority: {ticket.priority}\n"
                 f"Reporter: {ticket.reporter}   Assignee: {ticket.assignee}"
        )
        self.details_meta.pack(padx=14, pady=(10, 4), fill="x")

        formatted = self.jira.format_for_ai(ticket)
        self.details_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.details_text.delete("1.0", "end")
        self.details_text.insert("1.0", formatted)

        # Activate run button
        self.generate_btn.configure(
            state="normal",
            fg_color=COLORS["btn_run"],
            hover_color=COLORS["btn_run_hover"],
            text_color="#ffffff",
        )
        self.run_hint.configure(
            text="✔ Ticket ready — set App URL if needed, then click Run →",
            text_color=COLORS["warning"],
        )
        self._highlight_step("step4")

    def _fetch_fail(self, error_msg):
        self.fetch_btn.configure(state="normal", text="Fetch")
        self.fetch_status.configure(text=error_msg, text_color=COLORS["error"])

    def _start_generation(self):
        config.ai_provider = "github"
        config.github_model = self.model_var.get()
        config.target_base_url = self.url_var.get().strip()

        ticket_text = self.jira.format_for_ai(self.ticket)
        self.on_ticket_ready(self.ticket, ticket_text)
