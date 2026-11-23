"""Reproducible Windows one-folder PyInstaller build for the GUI entry point."""
from pathlib import Path
import tempfile
import sys

from PyInstaller import __main__ as pyinstaller


PROJECT_DIRECTORY = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(tempfile.mkdtemp(prefix="smart-file-organizer-build-"))


def main():
    if sys.platform != "win32":
        raise SystemExit("This build script is intended for Windows.")

    pyinstaller.run([
        "--noconfirm",
        "--distpath", str(OUTPUT_ROOT / "dist"),
        "--workpath", str(OUTPUT_ROOT / "work"),
        str(PROJECT_DIRECTORY / "SmartFileOrganizer.spec"),
    ])
    print(f"Build output: {OUTPUT_ROOT / 'dist' / 'SmartFileOrganizer'}")


if __name__ == "__main__":
    main()
