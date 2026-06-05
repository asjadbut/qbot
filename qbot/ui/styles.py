# Theme palettes — VS Code Dark 2026 and VS Code Light 2026

_DARK = {
    # ── Backgrounds ──────────────────────────────────────
    "bg_dark":        "#1e1e1e",   # editor background
    "bg_card":        "#252526",   # sidebar / panel
    "bg_input":       "#3c3c3c",   # input fields
    "bg_hover":       "#37373d",   # VS Code actual list-item hover

    # ── Accents ───────────────────────────────────────────
    "accent":         "#007acc",   # VS Code blue (buttons, active tabs)
    "accent_hover":   "#005f9e",   # darker blue on hover
    "accent2":        "#4ec9b0",   # VS Code teal
    "accent2_hover":  "#3aaf98",

    # ── Action colours ────────────────────────────────────
    "btn_fetch":      "#007acc",   # VS Code blue — clean, professional
    "btn_fetch_hover":"#005f9e",
    "btn_run":        "#22c55e",   # vivid green — "go"
    "btn_run_hover":  "#16a34a",
    "btn_neutral":    "#4a4a54",   # neutral grey-purple for secondary btns
    "btn_neutral_hover": "#5c5c6e",

    # ── Status ────────────────────────────────────────────
    "success":        "#22c55e",   # bright green
    "success_dim":    "#16a34a",
    "warning":        "#dcdcaa",   # VS Code yellow
    "error":          "#f48771",   # VS Code red/orange
    "info":           "#9cdcfe",   # VS Code light blue

    # ── Text ──────────────────────────────────────────────
    "text":           "#d4d4d4",
    "text_dim":       "#858585",
    "text_bright":    "#ffffff",
    "btn_text":       "#ffffff",   # text on accent-coloured buttons

    # ── Borders ───────────────────────────────────────────
    "border":         "#3c3c3c",
    "border_bright":  "#007acc",

    # ── Test result badges ────────────────────────────────
    "passed":         "#22c55e",
    "failed":         "#f48771",
    "skipped":        "#dcdcaa",
    "step_active":    "#007acc",

    # ── Syntax token colours ──────────────────────────────
    "token_keyword":  "#569cd6",
    "token_string":   "#ce9178",
    "token_comment":  "#6a9955",
    "token_fn":       "#dcdcaa",
}

_LIGHT = {
    # ── Backgrounds ──────────────────────────────────────
    "bg_dark":        "#ffffff",   # editor background
    "bg_card":        "#f3f3f3",   # sidebar / panel
    "bg_input":       "#ffffff",   # input fields
    "bg_hover":       "#e8e8e8",   # list-item hover

    # ── Accents ───────────────────────────────────────────
    "accent":         "#005fb8",   # VS Code Light blue
    "accent_hover":   "#004e99",
    "accent2":        "#16825d",   # teal
    "accent2_hover":  "#12714f",

    # ── Action colours ────────────────────────────────────
    "btn_fetch":      "#005fb8",
    "btn_fetch_hover":"#004e99",
    "btn_run":        "#16a34a",
    "btn_run_hover":  "#15803d",
    "btn_neutral":    "#c8c8c8",
    "btn_neutral_hover": "#b0b0b0",

    # ── Status ────────────────────────────────────────────
    "success":        "#16a34a",
    "success_dim":    "#15803d",
    "warning":        "#b8860b",   # dark goldenrod
    "error":          "#cd3131",   # VS Code Light red
    "info":           "#005fb8",

    # ── Text ──────────────────────────────────────────────
    "text":           "#3b3b3b",
    "text_dim":       "#6e7681",
    "text_bright":    "#000000",
    "btn_text":       "#ffffff",   # text on accent-coloured buttons

    # ── Borders ───────────────────────────────────────────
    "border":         "#d4d4d4",
    "border_bright":  "#005fb8",

    # ── Test result badges ────────────────────────────────
    "passed":         "#16a34a",
    "failed":         "#cd3131",
    "skipped":        "#b8860b",
    "step_active":    "#005fb8",

    # ── Syntax token colours ──────────────────────────────
    "token_keyword":  "#0000ff",
    "token_string":   "#a31515",
    "token_comment":  "#008000",
    "token_fn":       "#795e26",
}

# The active palette — mutable dict so all UI modules share the same reference
COLORS: dict[str, str] = dict(_DARK)


def set_theme(theme: str):
    """Switch the active color palette. theme must be 'dark' or 'light'."""
    source = _LIGHT if theme == "light" else _DARK
    COLORS.clear()
    COLORS.update(source)

FONTS = {
    "title":       ("Segoe UI",      24, "bold"),
    "heading":     ("Segoe UI",      15, "bold"),
    "body":        ("Segoe UI",      12),
    "body_bold":   ("Segoe UI",      12, "bold"),
    "small":       ("Segoe UI",      10),
    "mono":        ("Cascadia Code", 11),
    "mono_small":  ("Cascadia Code", 10),
}


def patch_dropdown_arrow(option_menu, color: str = "#ffffff"):
    """Persistently set the dropdown arrow color, surviving redraws."""
    original_draw = option_menu._draw

    def _patched_draw(*args, **kwargs):
        result = original_draw(*args, **kwargs)
        option_menu._canvas.itemconfig("dropdown_arrow", fill=color)
        return result

    option_menu._draw = _patched_draw
    option_menu._canvas.itemconfig("dropdown_arrow", fill=color)
