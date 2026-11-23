# Smart File Organizer

Smart File Organizer is a local Python application that sorts files into folders by extension. It includes a CustomTkinter desktop interface for reviewing a plan before organizing and a command-line interface for previews and scripted use.

## Problem and objective

Folders with mixed file types are hard to browse and maintain. This project provides a straightforward way to group common files while keeping the operation visible and predictable. It works on the selected folder's top level; it does not upload files or inspect file contents.

## Features

- Categorizes `.jpg`, `.jpeg`, and `.png` files as Images; `.pdf` as PDFs; `.mp3` as Music; `.mp4` as Videos; `.docx` and `.txt` as Documents; and other or extensionless files as Others.
- CustomTkinter GUI with folder selection, scanning, a destination preview, progress tracking, summary counts, and activity messages.
- CLI support through `organizer.py`, including `--dry-run` and `--log-file` options.
- GUI preview is enabled by default. The GUI asks for confirmation before moving files.
- Existing destination files are preserved; a number is added to incoming duplicate filenames (for example, `photo_1.jpg`).
- Directories are skipped, and individual filesystem errors are reported while processing continues.
- Actual organization runs record successes, skips, and errors in a log.

## Technologies

- Python 3, Tkinter, and CustomTkinter
- `os`, `shutil`, and `pathlib` for file operations
- `threading` and `queue` for background GUI work
- `argparse` and `logging` for the CLI and activity logs
- `unittest` for automated tests
- PyInstaller for Windows packaging

## Screenshots

No screenshot is currently included in the repository. Add a real screenshot here when one is available.

> Screenshot placeholder: Smart File Organizer desktop interface.

## Project structure

```text
smart-file-organizer/
├── .gitignore
├── README.md
├── SmartFileOrganizer.spec
├── build_windows.py
├── gui.py
├── organizer.py
├── requirements.txt
├── test_folder/                 # Sample files, not a test target
│   ├── Documents/
│   ├── Images/
│   ├── Music/
│   ├── PDFs/
│   └── Videos/
└── tests/
    ├── test_gui.py
    └── test_organizer.py
```

## Installation and setup

Use Python 3 on Windows. Tkinter must be available for the desktop interface. From PowerShell, clone the repository and install the dependencies in a virtual environment:

```powershell
git clone https://github.com/nih803/smart-file-organizer.git
Set-Location smart-file-organizer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt` installs CustomTkinter and PyInstaller.

## Run the GUI

From the project directory with the environment activated:

```powershell
python gui.py
```

Choose **Browse Folder**, scan the selected folder, and review the proposed destinations. Preview is enabled by default. Turn it off and choose **Organize Files** to proceed; the app asks for confirmation first.

## Run the CLI

Show the available options:

```powershell
python organizer.py --help
```

Preview a folder without moving files:

```powershell
python organizer.py "C:\Users\Alex\Downloads" --dry-run
```

After reviewing the preview, organize that folder:

```powershell
python organizer.py "C:\Users\Alex\Downloads"
```

The optional positional `folder` defaults to `test_folder`. A CLI run without `--dry-run` moves files without a confirmation prompt. The default log is `%LOCALAPPDATA%\SmartFileOrganizer\organizer.log` (or `~\.smart-file-organizer\organizer.log` when `LOCALAPPDATA` is unavailable). Supply `--log-file PATH` to choose another log path.

## Tests and verification

Run the complete test suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

The suite currently contains 30 tests. It covers categorization, previews, duplicate handling, logging, errors, non-recursive behavior, GUI folder safeguards, worker events, and packaging-related behavior. File operation tests use temporary directories rather than the bundled sample folder.

**Previously recorded results:** the last successful automated test run reported 30 tests passed. An earlier standalone executable build and smoke test succeeded. The latest working-tree state has not been revalidated: its attempted rebuild was blocked because Python was inaccessible to the build environment. These historical results do not certify the current working tree. No clean-machine test is claimed.

## Build the Windows executable

With Python available and the project dependencies installed, run:

```powershell
python build_windows.py
```

The script uses `SmartFileOrganizer.spec` to build the GUI as a one-folder Windows application. It creates a fresh unique directory under the system temporary directory for both PyInstaller's work files and distribution. The script prints the resulting directory; the executable is `SmartFileOrganizer\SmartFileOrganizer.exe` inside it. Keep the complete `SmartFileOrganizer` distribution folder together when running the app. The build script is Windows-only.

The existing build outputs are local artifacts and are not included in the repository.

## Safety and limitations

- The GUI starts in preview mode and asks for confirmation before moving files. CLI dry-run mode makes no file or log changes; a normal CLI run moves files directly.
- The application scans one folder level only. It skips subdirectories and does not organize their contents.
- Categorization uses filename extensions and does not inspect file content. Types without a dedicated mapping go to Others.
- Duplicate names are suffixed to avoid replacing an existing destination. The application does not coordinate with another process creating the same destination concurrently.
- Errors are reported and logged where possible; the organizer continues after individual move errors.
- The GUI rejects the application directory, drive roots, and common Windows system and installed-program directories.
- The tests do not automate native GUI mouse and keyboard interactions.
- The packaged application is an unsigned Windows build; Windows security software may show a warning.

## Future improvements

- Make categories and extension mappings configurable.
- Add optional recursive organization with explicit controls and preview.
- Add repository screenshots and expand native GUI interaction coverage.
