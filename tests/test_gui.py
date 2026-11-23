"""Tests for the desktop workflow using temporary folders and mocked dialogs."""
import os
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import gui
import organizer


class GuiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = self.temporary_directory.name
        self.folder = os.path.join(self.root, "selected")
        os.makedirs(self.folder)
        self.log_file = os.path.join(self.root, "organizer.log")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_worker_app(self):
        """Create an app shell for testing workers without opening a window."""
        app = gui.SmartFileOrganizerApp.__new__(gui.SmartFileOrganizerApp)
        app.events = queue.Queue()
        return app

    def create_file(self, filename, contents="sample"):
        path = os.path.join(self.folder, filename)
        with open(path, "w", encoding="utf-8") as file:
            file.write(contents)
        return path

    def test_native_windows_font_is_used_when_customtkinter_font_cannot_load(self):
        self.assertEqual(gui.ctk.ThemeManager.theme["CTkFont"]["family"], "Segoe UI")

    def test_gui_launcher_creates_and_runs_main_window(self):
        fake_app = Mock()
        with patch.object(gui, "SmartFileOrganizerApp", return_value=fake_app):
            gui.main()
        fake_app.mainloop.assert_called_once_with()

    def test_folder_selection_uses_standard_dialog(self):
        with patch.object(gui.filedialog, "askdirectory", return_value=self.folder) as dialog:
            self.assertEqual(gui.choose_folder(), self.folder)
        dialog.assert_called_once_with(
            title="Choose a folder to organize", mustexist=True
        )

    def test_folder_validation_rejects_empty_app_and_system_paths(self):
        with self.assertRaises(ValueError):
            gui.validate_target_folder("")
        with self.assertRaises(ValueError):
            gui.validate_target_folder(str(gui.APP_DIRECTORY))

        with patch.dict(os.environ, {"ProgramData": self.folder}):
            with self.assertRaises(ValueError):
                gui.validate_target_folder(self.folder)

    def test_valid_folder_is_returned_as_resolved_path(self):
        self.assertEqual(gui.validate_target_folder(self.folder), os.path.realpath(self.folder))

    def test_resource_path_uses_meipass_when_frozen(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "_MEIPASS", self.root, create=True
        ):
            path = gui.resource_path("customtkinter/assets/themes/blue.json")
        self.assertEqual(
            path,
            gui.Path(self.root) / "customtkinter/assets/themes/blue.json",
        )

    def test_default_log_file_is_in_writable_user_data_directory(self):
        log_file = gui.get_default_log_file()
        self.assertTrue(str(log_file).lower().find("smartfileorganizer") != -1)
        self.assertTrue(log_file.parent.is_dir())

    def test_empty_folder_scan_has_no_files(self):
        plan = organizer.scan_folder(self.folder, self.log_file)
        self.assertEqual(plan["items"], [])
        self.assertEqual(plan["directories"], [])

    def test_scan_plan_classifies_files_and_skips_nested_directories(self):
        self.create_file("photo.JPG")
        self.create_file("archive.unknown")
        self.create_file("LICENSE")
        nested = os.path.join(self.folder, "nested")
        os.makedirs(nested)
        self.create_file("inside.pdf")
        os.rename(os.path.join(self.folder, "inside.pdf"), os.path.join(nested, "inside.pdf"))

        plan = organizer.scan_folder(self.folder, self.log_file)
        items = {item["name"]: item for item in plan["items"]}

        self.assertEqual(items["photo.JPG"]["category"], "Images")
        self.assertEqual(items["archive.unknown"]["category"], "Others")
        self.assertEqual(items["LICENSE"]["category"], "Others")
        self.assertEqual(len(plan["directories"]), 1)
        self.assertNotIn("inside.pdf", items)

    def test_scan_worker_queues_plan_and_reports_scan_errors(self):
        self.create_file("photo.jpg")
        app = self.make_worker_app()
        worker = threading.Thread(target=app._scan_worker, args=(self.folder,))
        worker.start()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        event = app.events.get_nowait()
        self.assertEqual(event["type"], "scan_complete")
        self.assertEqual(event["plan"]["items"][0]["name"], "photo.jpg")

        with patch.object(organizer, "scan_folder", side_effect=PermissionError("blocked")):
            app._scan_worker(self.folder)
        error_event = app.events.get_nowait()
        self.assertEqual(error_event["type"], "scan_error")
        self.assertIn("Cannot access folder", error_event["message"])

    def test_operation_worker_queues_progress_summary_and_safe_preview(self):
        source = self.create_file("photo.jpg", "keep")
        self.create_file("archive.unknown")
        before_names = sorted(os.listdir(self.folder))
        app = self.make_worker_app()
        worker = threading.Thread(
            target=app._operation_worker, args=(self.folder, True)
        )
        worker.start()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        events = []
        while not app.events.empty():
            events.append(app.events.get_nowait())
        progress = [event for event in events if event["type"] == "progress"]
        completion = [event for event in events if event["type"] == "operation_complete"]

        self.assertEqual(len(completion), 1)
        self.assertEqual(completion[0]["summary"]["files_scanned"], 2)
        self.assertEqual(completion[0]["summary"]["categories"]["Images"], 1)
        self.assertEqual(completion[0]["summary"]["categories"]["Others"], 1)
        self.assertEqual(progress[-1]["completed"], progress[-1]["total"])
        self.assertEqual(sorted(os.listdir(self.folder)), before_names)
        self.assertTrue(os.path.isfile(source))
        self.assertFalse(os.path.exists(self.log_file))

    def test_operation_worker_converts_unexpected_errors_to_events(self):
        app = self.make_worker_app()
        with patch.object(organizer, "organize_folder", side_effect=RuntimeError("unexpected")):
            app._operation_worker(self.folder, False)
        event = app.events.get_nowait()
        self.assertEqual(event["type"], "operation_error")
        self.assertEqual(event["message"], "unexpected")

    def test_busy_guard_prevents_another_operation(self):
        app = gui.SmartFileOrganizerApp.__new__(gui.SmartFileOrganizerApp)
        app.busy = True
        self.assertIsNone(app.organize_or_preview())
    def test_preview_workflow_does_not_change_files(self):
        source = self.create_file("photo.jpg", "keep this file")
        before_names = os.listdir(self.folder)
        before_modified = os.stat(source).st_mtime_ns
        plan = organizer.scan_folder(self.folder, self.log_file)
        events = []

        summary = organizer.organize_folder(
            self.folder,
            dry_run=True,
            log_file=self.log_file,
            event_callback=events.append,
            print_report=False,
            print_output=False,
        )

        self.assertEqual(os.listdir(self.folder), before_names)
        self.assertEqual(os.stat(source).st_mtime_ns, before_modified)
        with open(source, encoding="utf-8") as file:
            self.assertEqual(file.read(), "keep this file")
        self.assertFalse(os.path.exists(os.path.join(self.folder, "Images")))
        self.assertFalse(os.path.exists(self.log_file))
        self.assertEqual(summary["organized"], 0)
        self.assertEqual(summary["categories"]["Images"], 1)
        self.assertEqual(plan["items"][0]["category"], "Images")
        self.assertTrue(any(event["type"] == "preview" for event in events))

    def test_actual_gui_workflow_moves_files_and_counts_categories(self):
        self.create_file("photo.jpg")
        self.create_file("unknown.xyz")
        events = []
        summary = organizer.organize_folder(
            self.folder,
            log_file=self.log_file,
            event_callback=events.append,
            print_report=False,
            print_output=False,
        )
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "Images", "photo.jpg")))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "Others", "unknown.xyz")))
        self.assertEqual(summary["organized"], 2)
        self.assertEqual(summary["categories"]["Images"], 1)
        self.assertEqual(summary["categories"]["Others"], 1)
        self.assertTrue(any(event["type"] == "success" for event in events))

    def test_duplicate_destination_is_preserved_and_suffixed(self):
        self.create_file("photo.jpg", "incoming")
        image_folder = os.path.join(self.folder, "Images")
        os.makedirs(image_folder)
        existing = os.path.join(image_folder, "photo.jpg")
        with open(existing, "w", encoding="utf-8") as file:
            file.write("keep existing")

        summary = organizer.organize_folder(
            self.folder, log_file=self.log_file, print_report=False, print_output=False
        )

        with open(existing, encoding="utf-8") as file:
            self.assertEqual(file.read(), "keep existing")
        self.assertTrue(os.path.isfile(os.path.join(image_folder, "photo_1.jpg")))
        self.assertEqual(summary["organized"], 1)

    def test_move_error_is_reported_and_later_file_is_organized(self):
        self.create_file("blocked.jpg")
        self.create_file("good.pdf")
        events = []
        real_move = organizer.shutil.move

        def fail_one_move(source, destination):
            if os.path.basename(source) == "blocked.jpg":
                raise PermissionError("simulated permission error")
            return real_move(source, destination)

        with patch.object(organizer.shutil, "move", side_effect=fail_one_move):
            summary = organizer.organize_folder(
                self.folder,
                log_file=self.log_file,
                event_callback=events.append,
                print_report=False,
                print_output=False,
            )
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["organized"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "blocked.jpg")))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "PDFs", "good.pdf")))
        self.assertTrue(any(event["type"] == "error" for event in events))

    def test_invalid_folder_scan_is_reported_without_raising(self):
        events = []
        summary = organizer.organize_folder(
            os.path.join(self.root, "missing"),
            dry_run=True,
            event_callback=events.append,
            print_report=False,
            print_output=False,
        )
        self.assertEqual(summary["failed"], 1)
        self.assertTrue(any(event["type"] == "error" for event in events))


if __name__ == "__main__":
    unittest.main()
