"""Cross-platform locations for app data and the Chrome browser.

Centralises the per-OS conventions so the rest of the codebase doesn't
hardcode Windows-only paths:

  Data directory
    Windows : %APPDATA%\\QBot
    macOS   : ~/Library/Application Support/QBot
    Linux   : $XDG_CONFIG_HOME/QBot  (fallback ~/.config/QBot)

  Chrome executable
    Probed at the standard install locations for each OS. When Chrome is
    not found, callers fall back to Playwright's bundled Chromium.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def app_data_dir() -> str:
    """Return the QBot data directory for the current operating system."""
    home = str(Path.home())
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or home
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:  # Linux / other POSIX
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return os.path.join(base, "QBot")


def chrome_candidates() -> list[str]:
    """Return likely Google Chrome executable paths for the current OS."""
    if sys.platform == "win32":
        return [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
        ]
    if sys.platform == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    # Linux / other POSIX — prefer PATH lookups, then common install paths.
    found = [
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    return [p for p in found if p] + [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
    ]
