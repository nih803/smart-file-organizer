import argparse
import logging
import os
import shutil
import sys
from pathlib import Path


CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png"],
    "PDFs": [".pdf"],
    "Music": [".mp3"],
    "Videos": [".mp4"],
    "Documents": [".docx", ".txt"],
}
CATEGORY_NAMES = list(CATEGORIES) + ["Others"]
PROTECTED_FILENAMES = {"organizer.py", "readme.md", ".gitignore", "requirements.txt"}
PROTECTED_EXTENSIONS = {".py"}


def get_category(filename):
    """Return the category that matches a file's extension."""
    _, extension = os.path.splitext(filename)
    extension = extension.lower()

    for category, extensions in CATEGORIES.items():
        if extension in extensions:
            return category

    return "Others"


def get_unique_destination(category_folder, filename):
    """Return an unused path, adding _1, _2, and so on if needed."""
    name, extension = os.path.splitext(filename)
    destination = os.path.join(category_folder, filename)
    suffix_number = 1

    while os.path.lexists(destination):
        unique_name = f"{name}_{suffix_number}{extension}"
        destination = os.path.join(category_folder, unique_name)
        suffix_number += 1

    return destination


def create_logger(log_file):
    """Create a file logger for successful moves, skips, and errors."""
    logger = logging.Logger("smart_file_organizer")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger, handler


def is_protected_file(folder, filename, log_file):
    """Keep project code, documentation, and the log out of category folders."""
    if filename.lower() in PROTECTED_FILENAMES:
        return True

    _, extension = os.path.splitext(filename)
    if extension.lower() in PROTECTED_EXTENSIONS:
        return True

    source_path = os.path.abspath(os.path.join(folder, filename))
    return source_path == os.path.abspath(log_file)


def make_summary():
    """Create counters used by the final report."""
    return {
        "files_scanned": 0,
        "organized": 0,
        "skipped": 0,
        "directories_skipped": 0,
        "failed": 0,
        "categories": {category: 0 for category in CATEGORY_NAMES},
    }


def notify_event(callback, event_type, message, **details):
    """Send an optional event to a UI or other caller."""
    if callback:
        callback({"type": event_type, "message": message, **details})


def scan_folder(folder, log_file="organizer.log"):
    """Build a read-only list of proposed destinations for one folder level."""
    plan = {"folder": os.path.abspath(folder), "items": [], "directories": []}
    files = os.listdir(folder)
    for index, filename in enumerate(files):
        source = os.path.abspath(os.path.join(folder, filename))
        extension = os.path.splitext(filename)[1] or "(none)"
        try:
            if os.path.isdir(source):
                plan["directories"].append(source)
                continue
            if is_protected_file(folder, filename, log_file):
                plan["items"].append({
                    "index": index, "name": filename, "extension": extension,
                    "category": "—", "source": source, "destination": "—",
                    "status": "Skipped", "message": "Protected file",
                })
                continue
            category = get_category(filename)
            destination = get_unique_destination(os.path.join(folder, category), filename)
            plan["items"].append({
                "index": index, "name": filename, "extension": extension,
                "category": category, "source": source,
                "destination": os.path.abspath(destination),
                "status": "Ready", "message": "",
            })
        except OSError as error:
            plan["items"].append({
                "index": index, "name": filename, "extension": extension,
                "category": "—", "source": source, "destination": "—",
                "status": "Error", "message": str(error),
            })
    return plan
def print_summary(summary, dry_run=False):
    """Print a short report of the operation."""
    mode = "Preview (no changes made)" if dry_run else "Organization complete"
    print("\nSMART FILE ORGANIZER - REPORT")
    print(f"Mode: {mode}")
    print(f"Files scanned: {summary['files_scanned']}")
    print(f"Files organized: {summary['organized']}")

    if dry_run:
        planned = sum(summary["categories"].values())
        print(f"Files planned: {planned}")

    print(f"Files skipped: {summary['skipped']}")
    print(f"Directories skipped: {summary['directories_skipped']}")
    print(f"Failed operations: {summary['failed']}")
    if dry_run:
        category_label = "Proposed files by category"
    else:
        category_label = "Files organized by category"
    print(f"{category_label}:")

    for category in CATEGORY_NAMES:
        print(f"  {category}: {summary['categories'][category]}")


def finish_operation(summary, dry_run, handler):
    """Print the final report and close the log file when one is open."""
    print_summary(summary, dry_run)
    if handler:
        handler.close()
    return summary


def get_folder_error_message(folder, error):
    """Turn common folder access errors into clear messages."""
    if isinstance(error, FileNotFoundError):
        return f"Folder does not exist: {folder}"
    if isinstance(error, PermissionError):
        return f"Cannot access folder '{folder}': {error}"
    if isinstance(error, NotADirectoryError):
        return f"Path is not a folder: {folder}"
    return f"Could not read folder '{folder}': {error}"


def get_default_log_file():
    """Return a writable per-user log path for GUI and CLI runs."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        log_directory = Path(local_app_data).expanduser() / "SmartFileOrganizer"
    else:
        log_directory = Path.home() / ".smart-file-organizer"
    log_directory.mkdir(parents=True, exist_ok=True)
    return log_directory / "organizer.log"


def organize_folder(
    folder="test_folder",
    dry_run=False,
    log_file="organizer.log",
    event_callback=None,
    progress_callback=None,
    print_report=True,
    print_output=True,
):
    """Preview or organize top-level files and return their operation counts."""
    summary = make_summary()
    logger = None
    handler = None

    def finish():
        if print_report:
            print_summary(summary, dry_run)
        if handler:
            handler.close()
        return summary

    if not dry_run:
        try:
            logger, handler = create_logger(log_file)
        except OSError as error:
            summary["failed"] += 1
            message = f"Cannot create log file '{log_file}': {error}"
            if print_output:
                print(f"Error: {message}")
            notify_event(event_callback, "error", message)
            return finish()

    try:
        files = os.listdir(folder)
    except OSError as error:
        summary["failed"] += 1
        message = get_folder_error_message(folder, error)
        if print_output:
            print(f"Error: {message}")
        if logger:
            logger.error("%s", message)
        notify_event(event_callback, "error", message)
        return finish()

    if not files:
        if print_output:
            print(f"Folder is empty: {folder}")
        if logger:
            logger.info("Folder is empty: %s", folder)
        notify_event(event_callback, "empty", f"Folder is empty: {folder}")
        return finish()

    for index, filename in enumerate(files):
        source = os.path.abspath(os.path.join(folder, filename))
        item = {"source": source, "name": filename}
        try:
            if os.path.isdir(source):
                summary["directories_skipped"] += 1
                if logger:
                    logger.info("SKIPPED directory: %s", source)
                notify_event(event_callback, "skipped", f"Skipped directory: {filename}")
                continue

            summary["files_scanned"] += 1
            if is_protected_file(folder, filename, log_file):
                summary["skipped"] += 1
                if logger:
                    logger.info("SKIPPED protected file: %s", source)
                item = {"source": source, "name": filename}
                notify_event(
                    event_callback, "skipped", f"Skipped protected file: {filename}",
                    item=item, status="Skipped",
                )
                continue

            category = get_category(filename)
            category_folder = os.path.join(folder, category)
            destination = get_unique_destination(category_folder, filename)
            item = {
                "source": source,
                "name": filename,
                "extension": os.path.splitext(filename)[1] or "(none)",
                "category": category,
                "destination": os.path.abspath(destination),
            }

            if dry_run:
                summary["categories"][category] += 1
                if print_output:
                    print(f"PREVIEW: {filename} -> {destination} ({category})")
                notify_event(
                    event_callback, "preview",
                    f"Preview: {filename} -> {destination}",
                    item=item, status="Preview",
                )
                continue

            os.makedirs(category_folder, exist_ok=True)
            destination = get_unique_destination(category_folder, filename)
            shutil.move(source, destination)
            summary["organized"] += 1
            summary["categories"][category] += 1
            item["destination"] = os.path.abspath(destination)
            if logger:
                logger.info("SUCCESS: %s -> %s", source, destination)
            notify_event(
                event_callback, "success", f"Moved {filename} to {category}",
                item=item, status="Moved",
            )
        except PermissionError as error:
            summary["failed"] += 1
            message = f"Permission denied for '{filename}': {error}"
            if print_output:
                print(f"Error: {message}")
            if logger:
                logger.error("ERROR: %s", message)
            notify_event(event_callback, "error", message, item=item, status="Error")
        except (OSError, shutil.Error) as error:
            summary["failed"] += 1
            message = f"Could not organize '{filename}': {error}"
            if print_output:
                print(f"Error: {message}")
            if logger:
                logger.error("ERROR: %s", message)
            notify_event(event_callback, "error", message, item=item, status="Error")
        finally:
            if progress_callback:
                progress_callback(index + 1, len(files))

    return finish()

def main():
    """Read command-line options and start the organizer."""
    parser = argparse.ArgumentParser(description="Organize files by category.")
    parser.add_argument(
        "folder",
        nargs="?",
        default="test_folder",
        help="folder to organize (default: test_folder)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview destinations without changing files",
    )
    parser.add_argument(
        "--log-file",
        default=str(get_default_log_file()),
        help="where to save the operation log (default: the per-user application data folder)",
    )
    args = parser.parse_args()
    organize_folder(args.folder, dry_run=args.dry_run, log_file=args.log_file)


if __name__ == "__main__":
    main()
