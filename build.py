"""Build QBot into a standalone .exe using PyInstaller."""
import subprocess
import sys
import os

def main():
    # Ensure pyinstaller is installed
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Find customtkinter path for data files
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "QBot",
        "--icon", "qbot.ico",
        "--add-data", f"{ctk_path};customtkinter/",
        "--add-data", "qbot.ico;.",
        "--add-data", "qbot_logo.png;.",
        "--hidden-import", "jira",
        "--hidden-import", "openai",
        "--hidden-import", "anthropic",
        "--hidden-import", "playwright",
        "--hidden-import", "PIL",
        "--hidden-import", "dotenv",
        "--hidden-import", "customtkinter",
        "--collect-all", "customtkinter",
        "--collect-all", "jira",
        "main.py",
    ]

    print("Building QBot.exe ...")
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=os.path.dirname(__file__))
    print("\n✅ Build complete! Find QBot.exe in the 'dist' folder.")


if __name__ == "__main__":
    main()
