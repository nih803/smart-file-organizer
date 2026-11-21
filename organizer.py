import argparse
import logging
import os
import shutil


CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png"],
    "PDFs": [".pdf"],
    "Music": [".mp3"],
    "Videos": [".mp4"],
    "Documents": [".docx", ".txt"],
}
CATEGORY_NAMES = list(CATEGORIES) + ["Others"]
PROTECTED_FILENAMES = {"organizer.py", "readme.md", ".gitignore"}
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


def organize_folder(folder="test_folder", dry_run=False, log_file="organizer.log"):
    """Preview or organize top-level files and return their operation counts."""
    summary = make_summary()
    logger = None
    handler = None

    # Preview does not create or update the log, keeping it read-only.
    if not dry_run:
        try:
            logger, handler = create_logger(log_file)
        except OSError as error:
            print(f"Error: cannot create log file '{log_file}': {error}")
            summary["failed"] += 1
            return finish_operation(summary, dry_run, handler)

    try:
        files = os.listdir(folder)
    except OSError as error:
        message = get_folder_error_message(folder, error)
        print(f"Error: {message}")
        if logger:
            logger.error("%s", message)
        summary["failed"] += 1
        return finish_operation(summary, dry_run, handler)

    if not files:
        print(f"Folder is empty: {folder}")
        if logger:
            logger.info("Folder is empty: %s", folder)
        return finish_operation(summary, dry_run, handler)

    for filename in files:
        source = os.path.join(folder, filename)

        try:
            # Match the existing behavior: do not enter nested directories.
            if os.path.isdir(source):
                summary["directories_skipped"] += 1
                if logger:
                    logger.info("SKIPPED directory: %s", source)
                continue

            summary["files_scanned"] += 1

            if is_protected_file(folder, filename, log_file):
                summary["skipped"] += 1
                if logger:
                    logger.info("SKIPPED protected file: %s", source)
                continue

            category = get_category(filename)
            category_folder = os.path.join(folder, category)
            destination = get_unique_destination(category_folder, filename)

            if dry_run:
                summary["categories"][category] += 1
                print(f"PREVIEW: {filename} -> {destination} ({category})")
                continue

            os.makedirs(category_folder, exist_ok=True)
            # Recheck after making the folder in case a file appeared meanwhile.
            destination = get_unique_destination(category_folder, filename)
            shutil.move(source, destination)
            summary["organized"] += 1
            summary["categories"][category] += 1
            logger.info("SUCCESS: %s -> %s", source, destination)
        except PermissionError as error:
            summary["failed"] += 1
            message = f"Permission denied for '{filename}': {error}"
            print(f"Error: {message}")
            if logger:
                logger.error("ERROR: %s", message)
        except (OSError, shutil.Error) as error:
            summary["failed"] += 1
            message = f"Could not organize '{filename}': {error}"
            print(f"Error: {message}")
            if logger:
                logger.error("ERROR: %s", message)

    return finish_operation(summary, dry_run, handler)


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
        default="organizer.log",
        help="where to save the operation log (default: organizer.log)",
    )
    args = parser.parse_args()
    organize_folder(args.folder, dry_run=args.dry_run, log_file=args.log_file)


if __name__ == "__main__":
    main()
