"""PE Suite entry point.

    .venv/Scripts/python.exe -m pesuite.app.main
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from pesuite.app.main_window import MainWindow
from pesuite.app.state import AppState
from pesuite.app.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PE Suite")
    apply_theme(app)

    state = AppState()
    window = MainWindow(state)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
