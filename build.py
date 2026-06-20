"""Build QBot into a standalone executable using PyInstaller.

Works on Windows (QBot.exe), macOS (QBot.app) and Linux (QBot binary).
"""
import subprocess
import sys
import os

def main():
    # Ensure pyinstaller is installed
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Find customtkinter path for data files
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)

    # PyInstaller's --add-data uses ';' on Windows and ':' elsewhere.
    sep = os.pathsep

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "QBot",
        "--add-data", f"{ctk_path}{sep}customtkinter/",
        "--add-data", f"qbot_logo.png{sep}.",
        "--add-data", f"qbot_logo_source.png{sep}.",
        "--hidden-import", "jira",
        "--hidden-import", "openai",
        "--hidden-import", "anthropic",
        "--hidden-import", "playwright",
        "--hidden-import", "PIL",
        "--hidden-import", "dotenv",
        "--hidden-import", "customtkinter",
        "--collect-all", "customtkinter",
        "--collect-all", "jira",
    ]

    # Platform-specific icon (Windows .ico / macOS .icns). Skipped if absent.
    if sys.platform == "win32" and os.path.isfile("qbot.ico"):
        cmd += ["--icon", "qbot.ico", "--add-data", f"qbot.ico{sep}."]
    elif sys.platform == "darwin" and os.path.isfile("qbot.icns"):
        cmd += ["--icon", "qbot.icns"]

    cmd.append("main.py")

    if sys.platform == "win32":
        artifact = "QBot.exe"
    elif sys.platform == "darwin":
        artifact = "QBot.app"
    else:
        artifact = "QBot"

    print(f"Building {artifact} ...")
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=os.path.dirname(__file__))
    print(f"\n✅ Build complete! Find {artifact} in the 'dist' folder.")


if __name__ == "__main__":
    main()

