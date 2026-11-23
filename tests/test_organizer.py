import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import organizer


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = self.temporary_directory.name
        self.folder = os.path.join(self.root, "input")
        os.makedirs(self.folder)
        self.log_file = os.path.join(self.root, "organizer.log")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def create_file(self, folder, filename, contents="sample"):
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as file:
            file.write(contents)
        return path

    def capture_run(self, **options):
        output = io.StringIO()
        log_file = options.pop("log_file", self.log_file)
        with contextlib.redirect_stdout(output):
            summary = organizer.organize_folder(
                self.folder, log_file=log_file, **options
            )
        return summary, output.getvalue()

    def test_preview_shows_destinations_without_changing_files(self):
        source = self.create_file(self.folder, "photo.jpg", "original")
        before_names = os.listdir(self.folder)
        before_modified = os.stat(source).st_mtime_ns
        with open(source, encoding="utf-8") as file:
            before_contents = file.read()

        summary, output = self.capture_run(dry_run=True)

        self.assertIn("photo.jpg ->", output)
        self.assertIn("Images", output)
        self.assertEqual(os.listdir(self.folder), before_names)
        self.assertEqual(os.stat(source).st_mtime_ns, before_modified)
        with open(source, encoding="utf-8") as file:
            self.assertEqual(file.read(), before_contents)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "Images")))
        self.assertFalse(os.path.exists(self.log_file))
        self.assertEqual(summary["organized"], 0)
        self.assertEqual(summary["categories"]["Images"], 1)

    def test_preview_accounts_for_existing_destination_without_changing_it(self):
        image_folder = os.path.join(self.folder, "Images")
        os.makedirs(image_folder)
        existing = self.create_file(image_folder, "photo.jpg", "keep this")
        incoming = self.create_file(self.folder, "photo.jpg", "incoming")
        before_names = os.listdir(self.folder)

        summary, output = self.capture_run(dry_run=True)

        self.assertIn("photo_1.jpg", output)
        self.assertEqual(os.listdir(self.folder), before_names)
        self.assertFalse(os.path.exists(os.path.join(image_folder, "photo_1.jpg")))
        with open(existing, encoding="utf-8") as file:
            self.assertEqual(file.read(), "keep this")
        with open(incoming, encoding="utf-8") as file:
            self.assertEqual(file.read(), "incoming")
        self.assertEqual(summary["organized"], 0)

    def test_summary_counts_successes_skips_and_categories(self):
        self.create_file(self.folder, "photo.jpg")
        self.create_file(self.folder, "notes.pdf")
        self.create_file(self.folder, "unknown.xyz")
        self.create_file(self.folder, "README.md")
        os.makedirs(os.path.join(self.folder, "nested"))

        summary, output = self.capture_run()

        self.assertEqual(summary["files_scanned"], 4)
        self.assertEqual(summary["organized"], 3)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["directories_skipped"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["categories"]["Images"], 1)
        self.assertEqual(summary["categories"]["PDFs"], 1)
        self.assertEqual(summary["categories"]["Others"], 1)
        self.assertIn("SMART FILE ORGANIZER - REPORT", output)

    def test_all_recognized_extensions_are_categorized(self):
        expected_categories = {
            "photo.jpg": "Images",
            "scan.JPEG": "Images",
            "icon.png": "Images",
            "notes.pdf": "PDFs",
            "song.mp3": "Music",
            "movie.mp4": "Videos",
            "assignment.docx": "Documents",
            "readme.txt": "Documents",
        }
        for filename in expected_categories:
            self.create_file(self.folder, filename)

        summary, _ = self.capture_run()

        for filename, category in expected_categories.items():
            self.assertTrue(os.path.isfile(os.path.join(self.folder, category, filename)))
        self.assertEqual(summary["organized"], len(expected_categories))
        self.assertEqual(summary["categories"]["Images"], 3)
        self.assertEqual(summary["categories"]["Documents"], 2)

    def test_duplicate_names_are_suffixed_without_overwriting(self):
        image_folder = os.path.join(self.folder, "Images")
        os.makedirs(image_folder)
        self.create_file(image_folder, "photo.jpg", "original")
        self.create_file(image_folder, "photo_1.jpg", "also original")
        self.create_file(self.folder, "photo.jpg", "incoming")

        summary, _ = self.capture_run()

        with open(os.path.join(image_folder, "photo.jpg"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "original")
        with open(os.path.join(image_folder, "photo_1.jpg"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "also original")
        with open(os.path.join(image_folder, "photo_2.jpg"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "incoming")
        self.assertEqual(summary["organized"], 1)

    def test_unknown_and_extensionless_files_go_to_others(self):
        self.create_file(self.folder, "archive.unknown")
        self.create_file(self.folder, "LICENSE")

        summary, _ = self.capture_run()

        archive = os.path.join(self.folder, "Others", "archive.unknown")
        license_file = os.path.join(self.folder, "Others", "LICENSE")
        self.assertTrue(os.path.isfile(archive))
        self.assertTrue(os.path.isfile(license_file))
        self.assertEqual(summary["categories"]["Others"], 2)

    def test_log_records_success_skips_and_errors_and_continues(self):
        self.create_file(self.folder, "README.md")
        self.create_file(self.folder, "blocked.jpg")
        self.create_file(self.folder, "good.pdf")
        real_move = organizer.shutil.move

        def fail_one_file(source, destination):
            if os.path.basename(source) == "blocked.jpg":
                raise PermissionError("simulated permission error")
            return real_move(source, destination)

        with patch.object(organizer.shutil, "move", side_effect=fail_one_file):
            summary, _ = self.capture_run()

        with open(self.log_file, encoding="utf-8") as log:
            contents = log.read()
        self.assertIn("SKIPPED protected file", contents)
        self.assertIn("ERROR:", contents)
        self.assertIn("SUCCESS:", contents)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["organized"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "blocked.jpg")))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "PDFs", "good.pdf")))

    def test_empty_and_invalid_folder_paths_are_reported(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            summary = organizer.organize_folder(empty, log_file=self.log_file)
        self.assertIn("Folder is empty", output.getvalue())
        self.assertEqual(summary["files_scanned"], 0)

        missing = os.path.join(self.root, "missing")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            summary = organizer.organize_folder(missing, log_file=self.log_file)
        self.assertIn("does not exist", output.getvalue())
        self.assertEqual(summary["failed"], 1)

    def test_inaccessible_folder_is_reported(self):
        output = io.StringIO()
        with patch.object(
            organizer.os, "listdir", side_effect=PermissionError("simulated")
        ):
            with contextlib.redirect_stdout(output):
                summary = organizer.organize_folder(
                    self.folder, log_file=self.log_file
                )
        self.assertIn("Cannot access folder", output.getvalue())
        self.assertEqual(summary["failed"], 1)

    def test_project_requirements_file_is_not_organized(self):
        requirements = self.create_file(self.folder, "requirements.txt", "customtkinter")
        summary = organizer.organize_folder(
            self.folder, log_file=self.log_file, print_report=False, print_output=False
        )
        self.assertTrue(os.path.isfile(requirements))
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["organized"], 0)

    def test_log_inside_target_is_not_organized(self):
        log_in_folder = os.path.join(self.folder, "organizer.log")

        summary, _ = self.capture_run(log_file=log_in_folder)

        self.assertTrue(os.path.isfile(log_in_folder))
        moved_log = os.path.join(self.folder, "Others", "organizer.log")
        self.assertFalse(os.path.exists(moved_log))
        self.assertEqual(summary["skipped"], 1)

    def test_nested_directories_are_not_processed(self):
        nested = os.path.join(self.folder, "nested")
        os.makedirs(nested)
        self.create_file(nested, "notes.txt")

        summary, _ = self.capture_run()

        self.assertTrue(os.path.isfile(os.path.join(nested, "notes.txt")))
        self.assertEqual(summary["files_scanned"], 0)
        self.assertEqual(summary["directories_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
