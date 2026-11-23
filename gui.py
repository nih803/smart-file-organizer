"""CustomTkinter desktop interface for Smart File Organizer."""
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

# Use the native Windows font if CustomTkinter cannot load its bundled Roboto font.
ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"

import organizer


def resource_path(relative_path):
    """Resolve bundled assets for normal Python and PyInstaller execution."""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


def get_app_directory():
    """Use the executable directory in a frozen app and the source directory otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_default_log_file():
    """Return a writable per-user log path and create its parent directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        log_directory = Path(local_app_data).expanduser() / "SmartFileOrganizer"
    else:
        log_directory = Path.home() / ".smart-file-organizer"
    log_directory.mkdir(parents=True, exist_ok=True)
    return log_directory / "organizer.log"


APP_DIRECTORY = get_app_directory()
LOG_FILE = get_default_log_file()
POLL_INTERVAL_MS = 100
TREE_BATCH_SIZE = 100


def choose_folder(dialog=None):
    """Open the standard folder picker and return its selected path."""
    if dialog is None:
        dialog = filedialog.askdirectory
    return dialog(title="Choose a folder to organize", mustexist=True)


def _is_same_or_child(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_target_folder(folder):
    """Check that a folder is readable and is not a common system location."""
    if not folder:
        raise ValueError("Choose a folder before scanning.")
    target = Path(folder).expanduser().resolve(strict=True)
    if not target.is_dir():
        raise ValueError("The selected path is not a folder.")
    if _is_same_or_child(target, APP_DIRECTORY):
        raise ValueError("Choose a folder outside the application directory.")
    if target.parent == target:
        raise ValueError("Choose a folder below the drive root.")

    protected_roots = []
    for variable in ("WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        value = os.environ.get(variable)
        if value:
            protected_roots.append(Path(value).resolve())
    for protected_root in protected_roots:
        if _is_same_or_child(target, protected_root):
            raise ValueError(
                "System and installed-program folders are protected. "
                "Choose a personal working folder instead."
            )

    with os.scandir(target):
        pass
    return str(target)


class SmartFileOrganizerApp(ctk.CTk):
    """Main window for scanning, previewing, and organizing files."""

    def __init__(self):
        super().__init__()
        self.title("Smart File Organizer")
        self.geometry("1180x820")
        self.minsize(920, 680)
        self.configure(fg_color=("#F3F6FB", "#111827"))

        self.selected_folder = tk.StringVar(value="")
        self.preview_only = tk.BooleanVar(value=True)
        self.events = queue.Queue()
        self.plan = None
        self.row_ids = {}
        self.busy = False
        self.pending_rows = []
        self.pending_plan = None
        self._build_interface()
        self._render_summary(organizer.make_summary())
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.after(POLL_INTERVAL_MS, self._process_events)

    def _build_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 10))
        ctk.CTkLabel(
            header, text="SMART FILE ORGANIZER",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#2563EB", "#60A5FA"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header, text="A clearer home for every file",
            font=ctk.CTkFont(size=27, weight="bold"),
        ).pack(anchor="w", pady=(4, 1))
        ctk.CTkLabel(
            header,
            text="Scan one folder level, review destinations, then organize with confidence.",
            font=ctk.CTkFont(size=14),
            text_color=("#667085", "#AAB4C3"),
        ).pack(anchor="w")

        folder_card = ctk.CTkFrame(self, corner_radius=14)
        folder_card.grid(row=1, column=0, sticky="ew", padx=28, pady=7)
        folder_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            folder_card, text="Folder to organize",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 5))
        self.folder_entry = ctk.CTkEntry(
            folder_card, textvariable=self.selected_folder,
            placeholder_text="Select a folder to begin", height=38, state="readonly",
        )
        self.folder_entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(0, 14))
        self.browse_button = ctk.CTkButton(
            folder_card, text="Browse Folder", width=138, height=38,
            command=self._browse_folder,
        )
        self.browse_button.grid(row=1, column=1, padx=6, pady=(0, 14))
        self.scan_button = ctk.CTkButton(
            folder_card, text="Scan Files", width=116, height=38,
            fg_color="#1D4ED8", hover_color="#1E40AF",
            command=self.scan_selected_folder,
        )
        self.scan_button.grid(row=1, column=2, padx=(6, 16), pady=(0, 14))

        self.summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.summary_frame.grid(row=2, column=0, sticky="ew", padx=28, pady=(4, 5))
        for column in range(4):
            self.summary_frame.grid_columnconfigure(column, weight=1, uniform="stats")
        self.summary_values = {}
        cards = (
            ("files_scanned", "FILES SCANNED"),
            ("organized", "ORGANIZED / PLANNED"),
            ("skipped", "SKIPPED"),
            ("failed", "ERRORS"),
        )
        for column, (key, label) in enumerate(cards):
            card = ctk.CTkFrame(self.summary_frame, corner_radius=12)
            card.grid(row=0, column=column, sticky="ew", padx=5)
            ctk.CTkLabel(
                card, text=label, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("#718096", "#9AA6B5"),
            ).pack(anchor="w", padx=13, pady=(9, 0))
            value = ctk.CTkLabel(card, text="0", font=ctk.CTkFont(size=24, weight="bold"))
            value.pack(anchor="w", padx=13, pady=(0, 8))
            self.summary_values[key] = value
        self.category_label = ctk.CTkLabel(
            self.summary_frame, text="", font=ctk.CTkFont(size=11),
            text_color=("#667085", "#AAB4C3"),
        )
        self.category_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=(7, 0))

        results = ctk.CTkFrame(self, corner_radius=14)
        results.grid(row=3, column=0, sticky="nsew", padx=28, pady=8)
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)
        title_row = ctk.CTkFrame(results, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        title_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            title_row, text="File preview", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(
            title_row, text="Choose a folder and scan it to see a preview.",
            font=ctk.CTkFont(size=12), text_color=("#667085", "#AAB4C3"),
        )
        self.status_label.grid(row=0, column=1, sticky="e")

        table_frame = ctk.CTkFrame(results, fg_color="transparent")
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Organizer.Treeview", rowheight=29, font=("Segoe UI", 10),
            background="#FFFFFF", fieldbackground="#FFFFFF",
            foreground="#263244", borderwidth=0,
        )
        style.configure(
            "Organizer.Treeview.Heading", font=("Segoe UI", 10, "bold"),
            background="#EAF0F8", foreground="#344054", relief="flat",
        )
        columns = ("name", "extension", "category", "destination", "status")
        self.file_table = ttk.Treeview(
            table_frame, columns=columns, show="headings", style="Organizer.Treeview",
        )
        headings = {
            "name": ("File name", 185),
            "extension": ("Extension", 90),
            "category": ("Category", 115),
            "destination": ("Proposed destination", 440),
            "status": ("Status", 100),
        }
        for column, (label, width) in headings.items():
            self.file_table.heading(column, text=label)
            self.file_table.column(column, width=width, minwidth=75, anchor="w")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.file_table.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.file_table.xview)
        self.file_table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.file_table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.file_table.tag_configure("error", foreground="#B42318")
        self.file_table.tag_configure("skipped", foreground="#667085")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=4, column=0, sticky="ew", padx=28, pady=(5, 8))
        controls.grid_columnconfigure(1, weight=1)
        self.preview_switch = ctk.CTkSwitch(
            controls, text="Preview only — do not move files",
            variable=self.preview_only, onvalue=True, offvalue=False,
            command=self._preview_mode_changed,
        )
        self.preview_switch.grid(row=0, column=0, sticky="w", padx=(0, 12), pady=(3, 9))
        self.progress_bar = ctk.CTkProgressBar(controls, height=9)
        self.progress_bar.grid(row=0, column=1, sticky="ew", padx=8, pady=(3, 9))
        self.progress_bar.set(0)
        self.progress_label = ctk.CTkLabel(
            controls, text="Ready", width=110, anchor="e", font=ctk.CTkFont(size=11)
        )
        self.progress_label.grid(row=0, column=2, padx=(8, 12), pady=(3, 9))

        self.organize_button = ctk.CTkButton(
            controls, text="Preview Plan", width=130, height=38,
            command=self.organize_or_preview,
        )
        self.organize_button.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.rescan_button = ctk.CTkButton(
            controls, text="Rescan", width=95, height=38,
            fg_color=("#E8EEF7", "#263244"),
            text_color=("#27364B", "#E5EAF2"),
            command=self.scan_selected_folder,
        )
        self.rescan_button.grid(row=1, column=1, sticky="w", padx=8)
        self.clear_button = ctk.CTkButton(
            controls, text="Clear Results", width=112, height=38,
            fg_color="transparent", border_width=1,
            text_color=("#475467", "#C5CEDA"), command=self.clear_results,
        )
        self.clear_button.grid(row=1, column=2, sticky="e")

        self.activity = ctk.CTkTextbox(
            self, height=92, corner_radius=12, wrap="word", state="disabled"
        )
        self.activity.grid(row=5, column=0, sticky="ew", padx=28, pady=(0, 20))

    def _browse_folder(self):
        selected = choose_folder()
        if not selected:
            self._add_activity("Folder selection cancelled.")
            return
        try:
            selected = validate_target_folder(selected)
        except (OSError, ValueError) as error:
            messagebox.showwarning("Folder not available", str(error), parent=self)
            self._add_activity(f"Folder rejected: {error}")
            return
        self.selected_folder.set(selected)
        self.plan = None
        self._clear_table()
        self._render_summary(organizer.make_summary())
        self.status_label.configure(text="Folder selected. Scan to review files.")
        self._add_activity(f"Selected folder: {selected}")
        self._update_controls()

    def scan_selected_folder(self):
        if self.busy:
            return
        try:
            folder = validate_target_folder(self.selected_folder.get())
        except (OSError, ValueError) as error:
            messagebox.showinfo("Choose a folder", str(error), parent=self)
            self._add_activity(f"Scan not started: {error}")
            return
        self._set_busy(True, "Scanning…")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.status_label.configure(text="Scanning one folder level…")
        self._add_activity("Scanning started.")
        threading.Thread(target=self._scan_worker, args=(folder,), daemon=True).start()

    def _scan_worker(self, folder):
        try:
            plan = organizer.scan_folder(folder, str(LOG_FILE))
        except OSError as error:
            self.events.put({
                "type": "scan_error",
                "message": organizer.get_folder_error_message(folder, error),
            })
            return
        self.events.put({"type": "scan_complete", "plan": plan})
    def _preview_mode_changed(self):
        self._update_controls()

    def organize_or_preview(self):
        if self.busy:
            return
        if not self.plan:
            messagebox.showinfo("Scan files first", "Scan a folder before starting.", parent=self)
            return
        ready_count = sum(item["status"] == "Ready" for item in self.plan["items"])
        if self.preview_only.get():
            dry_run = True
            self._add_activity("Generating preview; no files will be moved.")
        else:
            if ready_count == 0:
                messagebox.showinfo("Nothing to organize", "There are no eligible files to move.", parent=self)
                return
            confirmed = messagebox.askyesno(
                "Confirm organization",
                f"Move {ready_count} file(s) from:\n\n{self.plan['folder']}\n\n"
                "Files will be placed in category folders. Continue?",
                icon="warning",
                parent=self,
            )
            if not confirmed:
                self._add_activity("Organization cancelled; no files were moved.")
                return
            dry_run = False
            self._add_activity("Organization started.")

        self._set_busy(True, "Working…")
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        threading.Thread(
            target=self._operation_worker,
            args=(self.plan["folder"], dry_run),
            daemon=True,
        ).start()

    def _operation_worker(self, folder, dry_run):
        try:
            summary = organizer.organize_folder(
                folder,
                dry_run=dry_run,
                log_file=str(LOG_FILE),
                event_callback=self.events.put,
                progress_callback=lambda done, total: self.events.put({
                    "type": "progress", "completed": done, "total": total,
                }),
                print_report=False,
                print_output=False,
            )
        except Exception as error:
            self.events.put({"type": "operation_error", "message": str(error)})
            return
        self.events.put({
            "type": "operation_complete", "summary": summary, "dry_run": dry_run,
        })

    def clear_results(self):
        if self.busy:
            return
        self.plan = None
        self._clear_table()
        self._render_summary(organizer.make_summary())
        self.progress_bar.set(0)
        self.progress_label.configure(text="Ready")
        self.status_label.configure(text="Results cleared. The selected folder is unchanged.")
        self._add_activity("Results cleared.")
        self._update_controls()

    def _clear_table(self):
        for row_id in self.file_table.get_children():
            self.file_table.delete(row_id)
        self.row_ids.clear()

    def _set_busy(self, busy, progress_text="Ready"):
        self.busy = busy
        self.progress_label.configure(text=progress_text)
        self._update_controls()

    def _update_controls(self):
        state = "disabled" if self.busy else "normal"
        for widget in (
            self.browse_button, self.scan_button, self.preview_switch,
            self.rescan_button, self.clear_button,
        ):
            widget.configure(state=state)
        has_rows = bool(self.plan and self.plan["items"])
        button_text = "Preview Plan" if self.preview_only.get() else "Organize Files"
        button_state = "normal" if not self.busy and has_rows else "disabled"
        self.organize_button.configure(text=button_text, state=button_state)

    def _render_summary(self, summary, preview=False):
        self.summary_values["files_scanned"].configure(text=str(summary["files_scanned"]))
        shown_count = (
            sum(summary["categories"].values()) if preview else summary["organized"]
        )
        self.summary_values["organized"].configure(text=str(shown_count))
        self.summary_values["skipped"].configure(text=str(summary["skipped"]))
        self.summary_values["failed"].configure(text=str(summary["failed"]))
        self.category_label.configure(text=self._category_text(summary["categories"]))

    def _category_text(self, categories):
        return "   •   ".join(
            f"{category}: {categories.get(category, 0)}"
            for category in organizer.CATEGORY_NAMES
        )

    def _add_activity(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.activity.configure(state="normal")
        self.activity.insert("end", f"{timestamp}  {message}\n")
        self.activity.see("end")
        self.activity.configure(state="disabled")

    def _close_window(self):
        if self.busy:
            messagebox.showinfo(
                "Operation in progress",
                "Wait for the current scan or organization to finish before closing.",
                parent=self,
            )
            return
        self.destroy()

    def _process_events(self):
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._process_events)

    def _handle_event(self, event):
        event_type = event["type"]
        if event_type == "scan_complete":
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.pending_plan = event["plan"]
            self.pending_rows = list(self.pending_plan["items"])
            self._clear_table()
            summary = organizer.make_summary()
            summary["files_scanned"] = len(self.pending_rows)
            summary["directories_skipped"] = len(self.pending_plan["directories"])
            for item in self.pending_rows:
                if item["status"] == "Skipped":
                    summary["skipped"] += 1
                elif item["status"] == "Error":
                    summary["failed"] += 1
                else:
                    summary["categories"][item["category"]] += 1
            self.pending_plan["summary"] = summary
            self._render_summary(summary, preview=True)
            self.status_label.configure(
                text=f"{summary['files_scanned']} file(s) scanned. Review proposed destinations."
            )
            self._add_activity(f"Scan complete: {summary['files_scanned']} file(s) detected.")
            self._insert_next_batch()
        elif event_type == "scan_error":
            self.progress_bar.stop()
            self._add_activity(f"Error: {event['message']}")
            self.status_label.configure(text="The folder could not be scanned.")
            self._set_busy(False)
            messagebox.showerror("Scan failed", event["message"], parent=self)
        elif event_type in ("success", "skipped", "error", "preview"):
            self._add_activity(event["message"])
            item = event.get("item")
            if item:
                row_id = self.row_ids.get(item.get("source"))
                if row_id:
                    values = list(self.file_table.item(row_id, "values"))
                    values[4] = event.get("status", event_type.title())
                    if item.get("destination") and item["destination"] != "—":
                        values[3] = item["destination"]
                    tag = "error" if event_type == "error" else "skipped" if event_type == "skipped" else ""
                    self.file_table.item(row_id, values=values, tags=(tag,))
        elif event_type == "progress":
            total = event["total"]
            completed = event["completed"]
            self.progress_bar.set(completed / total if total else 1)
            self.progress_label.configure(text=f"{completed} / {total}")
        elif event_type == "empty":
            self._add_activity(event["message"])
        elif event_type == "operation_complete":
            dry_run = event["dry_run"]
            summary = event["summary"]
            self._render_summary(summary, preview=dry_run)
            self.progress_bar.set(1)
            result = "Preview ready" if dry_run else "Complete"
            self.progress_label.configure(text=result)
            self.status_label.configure(
                text="Preview generated — no files changed."
                if dry_run else "Organization finished. Review the results below."
            )
            self._add_activity(
                "Preview generated; no files changed."
                if dry_run else "Organization completed."
            )
            self._add_activity(self._category_text(summary["categories"]))
            self._set_busy(False, result)
            if not dry_run and summary["failed"] == 0:
                messagebox.showinfo(
                    "Organization complete",
                    f"Organized {summary['organized']} file(s).",
                    parent=self,
                )
            elif not dry_run:
                messagebox.showwarning(
                    "Organization finished with errors",
                    f"Organized {summary['organized']} file(s); "
                    f"{summary['failed']} operation(s) failed. See the activity log.",
                    parent=self,
                )
        elif event_type == "operation_error":
            self._add_activity(f"Error: {event['message']}")
            self._set_busy(False)
            messagebox.showerror("Operation failed", event["message"], parent=self)

    def _insert_next_batch(self):
        batch = self.pending_rows[:TREE_BATCH_SIZE]
        self.pending_rows = self.pending_rows[TREE_BATCH_SIZE:]
        for item in batch:
            row_id = self.file_table.insert(
                "",
                "end",
                values=(
                    item["name"], item["extension"], item["category"],
                    item["destination"], item["status"],
                ),
                tags=("error" if item["status"] == "Error" else "skipped" if item["status"] == "Skipped" else "",),
            )
            self.row_ids[item["source"]] = row_id

        if self.pending_rows:
            self.after(1, self._insert_next_batch)
            return

        self.plan = self.pending_plan
        self.pending_plan = None
        self._add_activity("Preview generated. Review it before organizing.")
        if not self.plan["items"]:
            self._add_activity("No top-level files were found to organize.")
        self._set_busy(False)


def main():
    """Launch the desktop application."""
    app = SmartFileOrganizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
