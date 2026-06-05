import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from qbot.ui.app import QBotApp


def main():
    app = QBotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
