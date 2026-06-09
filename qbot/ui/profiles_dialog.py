"""Team profile editor dialog.

Lets each QA team customise the AI's mindset for their app:
  - Style rules (verbose vs minimal, edge case appetite)
  - Tech stack hints (framework-specific patterns)
  - Selector conventions
  - Product glossary
  - Free-form extra instructions

Profiles are stored in %APPDATA%/QBot/profiles.json.
"""

import re
import sys
from typing import List, Optional

import customtkinter as ctk
from tkinter import messagebox

from qbot.ui.styles import COLORS, FONTS, patch_dropdown_arrow
from qbot.profiles import (
    Profile,
    DEFAULT_PROFILE_ID,
    load_profiles,
    save_profiles,
)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "profile"


def _force_dark_titlebar(window) -> None:
    """Force the Windows native title bar to dark mode (DWMWA_USE_IMMERSIVE_DARK_MODE).

    customtkinter's CTkToplevel applies this on init but a nested toplevel
    (a dialog opened from another dialog) sometimes misses it. Re-applying
    after the window is mapped is harmless on other platforms.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = wintypes.HWND(int(window.frame(), 16))
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE on Win10 20H1+; 19 on older builds.
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass


class ProfilesDialog(ctk.CTkToplevel):
    """Manage team profiles — list on the left, editor on the right."""

    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self.title("Team Profiles")
        self.geometry("980x640")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = (sw - 980) // 2
        py = (sh - 640) // 2
        self.geometry(f"980x640+{px}+{py}")

        self.on_save_callback = on_save
        self.profiles: List[Profile] = load_profiles()
        self.current_id: Optional[str] = self.profiles[0].id if self.profiles else None
        self._dirty = False

        self._build_ui()
        self._load_profile_into_form(self.current_id)

        # Re-apply dark title bar after window is realised (fixes nested CTkToplevel)
        self.after(50, lambda: _force_dark_titlebar(self))

    # ── UI ──

    def _build_ui(self):
        # Title bar
        titlebar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=40, corner_radius=0)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        ctk.CTkLabel(
            titlebar, text="  Team Profiles", font=FONTS["body_bold"],
            text_color=COLORS["text"],
        ).pack(side="left", padx=10)
        ctk.CTkLabel(
            titlebar,
            text="Per-team QA mindset for AI test generation",
            font=FONTS["small"], text_color=COLORS["text_dim"],
        ).pack(side="left", padx=4)

        body = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        body.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        # ── LEFT: profile list ──
        left = ctk.CTkFrame(
            body, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1, width=240,
        )
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="PROFILES", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=12, pady=(12, 4), anchor="w")

        self.list_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0, width=216,
        )
        self.list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Action buttons
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 10))
        ctk.CTkButton(
            btn_row, text="+ New", width=66, height=28,
            font=FONTS["small"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._new_profile,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text="Clone", width=66, height=28,
            font=FONTS["small"], fg_color=COLORS["btn_neutral"],
            hover_color=COLORS["btn_neutral_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._clone_profile,
        ).pack(side="left", padx=(0, 4))
        self.delete_btn = ctk.CTkButton(
            btn_row, text="Delete", width=66, height=28,
            font=FONTS["small"], fg_color=COLORS["btn_neutral"],
            hover_color=COLORS["error"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._delete_profile,
        )
        self.delete_btn.pack(side="left")

        # ── RIGHT: editor form ──
        right = ctk.CTkFrame(
            body, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1,
        )
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self.editor = ctk.CTkScrollableFrame(right, fg_color="transparent", corner_radius=0)
        self.editor.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_editor()

        # ── BOTTOM: save / close ──
        bottom = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        bottom.pack(fill="x", padx=10, pady=(8, 12))

        ctk.CTkButton(
            bottom, text="Save Changes", width=140, height=36,
            font=FONTS["body_bold"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color=COLORS["btn_text"],
            corner_radius=4, command=self._save_all,
        ).pack(side="left")

        ctk.CTkButton(
            bottom, text="Close", width=100, height=36,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
            hover_color=COLORS["btn_neutral"], corner_radius=4,
            command=self._on_close,
        ).pack(side="left", padx=(8, 0))

        self.status_label = ctk.CTkLabel(
            bottom, text="", font=FONTS["small"], text_color=COLORS["success"],
        )
        self.status_label.pack(side="left", padx=16)

        self._refresh_list()

    def _build_editor(self):
        # Name
        ctk.CTkLabel(
            self.editor, text="PROFILE NAME", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=4, pady=(4, 2), anchor="w")
        self.name_entry = ctk.CTkEntry(
            self.editor, height=32, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text"], corner_radius=4,
        )
        self.name_entry.pack(fill="x", padx=4, pady=(0, 8))
        self.name_entry.bind("<KeyRelease>", lambda e: self._mark_dirty())

        # Description
        ctk.CTkLabel(
            self.editor, text="DESCRIPTION", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=4, pady=(4, 2), anchor="w")
        self.desc_entry = ctk.CTkEntry(
            self.editor, height=32, font=FONTS["body"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text"], corner_radius=4,
            placeholder_text="What team / app is this profile for?",
        )
        self.desc_entry.pack(fill="x", padx=4, pady=(0, 12))
        self.desc_entry.bind("<KeyRelease>", lambda e: self._mark_dirty())

        # Big text fields
        self.style_box = self._textarea(
            "STYLE RULES — your team's QA mindset",
            "How should the AI scope tests? Verbose vs minimal, when to write negative cases, "
            "what kinds of tests to never generate. One bullet per line.",
            height=160,
        )
        self.tech_box = self._textarea(
            "TECH STACK & APP-SPECIFIC PATTERNS",
            "Framework quirks the AI must respect. e.g. ASP.NET WebForms postback waits, "
            "Vue v-if removal, Next.js client-side nav, etc.",
            height=140,
        )
        self.selector_box = self._textarea(
            "SELECTOR & INTERACTION CONVENTIONS",
            "Preferred locator strategy: data-testid, role-based, legacy IDs. "
            "How custom checkboxes/dropdowns work in your app.",
            height=140,
        )
        self.glossary_box = self._textarea(
            "PRODUCT GLOSSARY",
            "Domain terms the AI should know. Format: term — definition (one per line).",
            height=100,
        )
        self.extra_box = self._textarea(
            "EXTRA INSTRUCTIONS",
            "Anything else: feature flags, env-specific behaviour, do/don't lists.",
            height=100,
        )

    def _textarea(self, label: str, hint: str, height: int) -> ctk.CTkTextbox:
        ctk.CTkLabel(
            self.editor, text=label, font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=4, pady=(8, 2), anchor="w")
        ctk.CTkLabel(
            self.editor, text=hint, font=FONTS["small"],
            text_color=COLORS["text_dim"], wraplength=620, justify="left",
        ).pack(padx=4, pady=(0, 4), anchor="w")
        box = ctk.CTkTextbox(
            self.editor, height=height, font=FONTS["mono_small"],
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            border_width=1, text_color=COLORS["text"], corner_radius=4,
            wrap="word",
        )
        box.pack(fill="x", padx=4, pady=(0, 6))
        box.bind("<KeyRelease>", lambda e: self._mark_dirty())
        return box

    # ── List management ──

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        for p in self.profiles:
            is_active = p.id == self.current_id
            row = ctk.CTkFrame(
                self.list_frame,
                fg_color=COLORS["accent"] if is_active else COLORS["bg_input"],
                corner_radius=4,
            )
            row.pack(fill="x", pady=2, padx=2)

            label = ctk.CTkLabel(
                row, text=p.name or p.id, font=FONTS["body"],
                text_color=COLORS["btn_text"] if is_active else COLORS["text"],
                anchor="w",
            )
            label.pack(fill="x", padx=10, pady=8)
            label.bind("<Button-1>", lambda e, pid=p.id: self._select(pid))
            row.bind("<Button-1>", lambda e, pid=p.id: self._select(pid))

        # Disable delete for default
        is_default = self.current_id == DEFAULT_PROFILE_ID
        self.delete_btn.configure(state="disabled" if is_default else "normal")

    def _select(self, profile_id: str):
        if self._dirty:
            ok = messagebox.askyesno(
                "Unsaved changes",
                "You have unsaved changes in the current profile. Discard them?",
                parent=self,
            )
            if not ok:
                return
        self._capture_into_current()  # capture even if not dirty (no-op)
        self._dirty = False
        self.current_id = profile_id
        self._load_profile_into_form(profile_id)
        self._refresh_list()
        self.status_label.configure(text="")

    def _new_profile(self):
        base = "New Team Profile"
        name = base
        i = 2
        existing = {p.name for p in self.profiles}
        while name in existing:
            name = f"{base} {i}"
            i += 1

        new_id = self._unique_id(_slugify(name))
        new_profile = Profile(id=new_id, name=name, description="")
        self.profiles.append(new_profile)
        self.current_id = new_id
        self._dirty = True
        self._load_profile_into_form(new_id)
        self._refresh_list()

    def _clone_profile(self):
        if not self.current_id:
            return
        self._capture_into_current()
        src = next(p for p in self.profiles if p.id == self.current_id)
        new_name = f"{src.name} (copy)"
        new_id = self._unique_id(_slugify(new_name))
        clone = Profile(
            id=new_id, name=new_name, description=src.description,
            tech_stack=src.tech_stack, style_rules=src.style_rules,
            selector_conventions=src.selector_conventions,
            glossary=src.glossary, extra_instructions=src.extra_instructions,
        )
        self.profiles.append(clone)
        self.current_id = new_id
        self._dirty = True
        self._load_profile_into_form(new_id)
        self._refresh_list()

    def _delete_profile(self):
        if self.current_id == DEFAULT_PROFILE_ID:
            return
        target = next((p for p in self.profiles if p.id == self.current_id), None)
        if target is None:
            return
        ok = messagebox.askyesno(
            "Delete profile",
            f"Delete profile '{target.name}'?\nThis cannot be undone.",
            parent=self,
        )
        if not ok:
            return
        self.profiles = [p for p in self.profiles if p.id != self.current_id]
        self.current_id = DEFAULT_PROFILE_ID
        self._dirty = True  # mark so saving reflects deletion
        self._load_profile_into_form(self.current_id)
        self._refresh_list()

    def _unique_id(self, base: str) -> str:
        existing = {p.id for p in self.profiles}
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    # ── Form ↔ profile binding ──

    def _load_profile_into_form(self, profile_id: Optional[str]):
        if profile_id is None:
            return
        p = next((x for x in self.profiles if x.id == profile_id), None)
        if p is None:
            return

        is_default = p.id == DEFAULT_PROFILE_ID
        # The default profile is shipped — let users see it but not rename it.
        # Editing its content is allowed (so users can tweak the baseline).
        self.name_entry.configure(state="normal")
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, p.name)
        if is_default:
            self.name_entry.configure(state="disabled")

        self.desc_entry.delete(0, "end")
        self.desc_entry.insert(0, p.description)

        for box, val in [
            (self.style_box, p.style_rules),
            (self.tech_box, p.tech_stack),
            (self.selector_box, p.selector_conventions),
            (self.glossary_box, p.glossary),
            (self.extra_box, p.extra_instructions),
        ]:
            box.delete("1.0", "end")
            if val:
                box.insert("1.0", val)

        self._dirty = False

    def _capture_into_current(self):
        if not self.current_id:
            return
        p = next((x for x in self.profiles if x.id == self.current_id), None)
        if p is None:
            return
        if p.id != DEFAULT_PROFILE_ID:
            new_name = self.name_entry.get().strip() or p.name
            p.name = new_name
        p.description = self.desc_entry.get().strip()
        p.style_rules = self.style_box.get("1.0", "end").rstrip()
        p.tech_stack = self.tech_box.get("1.0", "end").rstrip()
        p.selector_conventions = self.selector_box.get("1.0", "end").rstrip()
        p.glossary = self.glossary_box.get("1.0", "end").rstrip()
        p.extra_instructions = self.extra_box.get("1.0", "end").rstrip()

    def _mark_dirty(self):
        self._dirty = True
        self.status_label.configure(text="Unsaved changes", text_color=COLORS["warning"])

    # ── Save / close ──

    def _save_all(self):
        self._capture_into_current()
        # Validate names are unique and non-empty
        seen = set()
        for p in self.profiles:
            if not p.name.strip():
                messagebox.showerror(
                    "Invalid profile",
                    f"Profile '{p.id}' has no name.",
                    parent=self,
                )
                return
            if p.name in seen:
                messagebox.showerror(
                    "Duplicate name",
                    f"Profile name '{p.name}' is used more than once.",
                    parent=self,
                )
                return
            seen.add(p.name)

        save_profiles(self.profiles)
        self._dirty = False
        self.status_label.configure(text="Saved", text_color=COLORS["success"])
        if self.on_save_callback:
            self.on_save_callback()

    def _on_close(self):
        if self._dirty:
            ok = messagebox.askyesno(
                "Unsaved changes",
                "You have unsaved changes. Close anyway?",
                parent=self,
            )
            if not ok:
                return
        self.destroy()
