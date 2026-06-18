"""Rebuild Excel workbooks for both demo projects."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gantt_builder import api


def main():
    for name in ("small_demo", "npde_demo"):
        path = ROOT / "examples" / f"{name}.json"
        project = api.load_project(path)
        out = api.build_excel(project, output_dir=ROOT / "output")
        print(f"{name} -> {out}")


if __name__ == "__main__":
    main()
