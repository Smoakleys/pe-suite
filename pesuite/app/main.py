"""PE Suite entry point.

Preferred launch (from the repo root, using the project venv):

    .venv/Scripts/python.exe -m pesuite.app.main

Running this file directly also works — the block below puts the repo root on
sys.path so `import pesuite` resolves regardless of how Python was invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root = two levels up from this file (pesuite/app/main.py). Ensure it's importable
# even when launched as a script (python path\to\main.py) rather than as a module.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _ensure_venv() -> None:
    """If the engine deps aren't importable but the project venv has them, re-exec
    through the venv interpreter. Lets `python pesuite\\app\\main.py` work even when
    the caller used a system Python that lacks the project's dependencies."""
    import importlib.util
    if importlib.util.find_spec("gantt_builder") is not None:
        return  # deps already available — nothing to do
    if sys.platform == "win32":
        venv_py = _REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = _REPO_ROOT / ".venv" / "bin" / "python"
    # Avoid an infinite loop if we're already the venv interpreter.
    if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
        import os
        os.execv(str(venv_py), [str(venv_py), "-m", "pesuite.app.main", *sys.argv[1:]])


_ensure_venv()

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
