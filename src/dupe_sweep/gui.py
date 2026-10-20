"""Tkinter desktop interface for scanning and safe duplicate cleanup."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cleaner import clean_duplicates
from .finder import DuplicateGroup, find_duplicates
from .folders import discover_user_folders, protected_paths
from .logging_config import configure_logging
from .rules import KeepStrategy, choose_keep

LOGGER = logging.getLogger(__name__)


class DupeSweepApp:
    """Interactive duplicate scanner and confirmed Recycle Bin cleaner."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("dupe-sweep — Duplicate File Finder")
        self.root.geometry("920x680")
        self.root.minsize(720, 480)
        self.roots = discover_user_folders()
        self.groups: list[DuplicateGroup] = []
        self.removals: dict[Path, tk.BooleanVar] = {}
        self._build_ui()
        configure_logging()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="dupe-sweep", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Find content-identical files and review every removal.").pack(anchor="w", pady=(0, 12))

        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        self.folder_label = ttk.Label(controls, text=self._folder_text(), wraplength=620)
        self.folder_label.pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text="Add folder…", command=self._add_folder).pack(side="right", padx=(8, 0))
        ttk.Button(controls, text="Reset defaults", command=self._reset_folders).pack(side="right")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=12)
        self.scan_button = ttk.Button(actions, text="Scan for duplicates", command=self.scan)
        self.scan_button.pack(side="left")
        self.clean_button = ttk.Button(actions, text="Move selected to Recycle Bin", command=self.clean, state="disabled")
        self.clean_button.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=180)
        self.progress.pack(side="right")

        self.status = tk.StringVar(value="Ready. Scans never delete files.")
        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(0, 8))
        result_shell = ttk.Frame(outer)
        result_shell.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(result_shell, highlightthickness=0)
        scrollbar = ttk.Scrollbar(result_shell, orient="vertical", command=self.canvas.yview)
        self.results = ttk.Frame(self.canvas)
        self.results.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.results, anchor="nw")
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.canvas_window, width=event.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", lambda event: self.canvas.yview_scroll(int(-event.delta / 120), "units"))

    def _folder_text(self) -> str:
        return "\n".join(str(path) for path in self.roots) if self.roots else "No folders selected"

    def _add_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose a folder to scan")
        if selected:
            path = Path(selected)
            if path not in self.roots:
                self.roots.append(path)
                self.folder_label.configure(text=self._folder_text())

    def _reset_folders(self) -> None:
        self.roots = discover_user_folders()
        self.folder_label.configure(text=self._folder_text())

    def scan(self) -> None:
        if not self.roots:
            messagebox.showinfo("Choose folders", "Add at least one folder to scan.")
            return
        self.scan_button.configure(state="disabled")
        self.clean_button.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Scanning files…")
        for child in self.results.winfo_children():
            child.destroy()

        def work() -> None:
            count = 0

            def on_file(_path: Path) -> None:
                nonlocal count
                count += 1
                if count % 25 == 0:
                    self.root.after(0, lambda current=count: self.status.set(f"Scanning… {current:,} files visited"))

            try:
                found = find_duplicates(self.roots, exclusions=tuple(protected_paths()), on_file=on_file)
                self.root.after(0, lambda: self._show_results(found, count))
            except Exception as error:
                LOGGER.exception("Scan failed")
                self.root.after(0, lambda current_error=error: self._scan_failed(current_error))

        threading.Thread(target=work, name="dupe-sweep-scan", daemon=True).start()

    def _scan_failed(self, error: Exception) -> None:
        self.progress.stop()
        self.scan_button.configure(state="normal")
        messagebox.showerror("Scan failed", str(error))
        self.status.set("Scan failed. See logs/dupe-sweep.log for details.")

    def _show_results(self, groups: list[DuplicateGroup], count: int) -> None:
        self.progress.stop()
        self.scan_button.configure(state="normal")
        self.groups = groups
        self.removals.clear()
        if not groups:
            ttk.Label(self.results, text="No duplicate files found.", padding=12).pack(anchor="w")
        for index, group in enumerate(groups, start=1):
            keep = choose_keep(group, KeepStrategy.OLDEST)
            block = ttk.LabelFrame(self.results, text=f"Group {index} · {group.size:,} bytes · {len(group.files)} copies")
            block.pack(fill="x", padx=4, pady=5)
            for path in group.files:
                row = ttk.Frame(block, padding=(8, 3))
                row.pack(fill="x")
                if path == keep:
                    ttk.Label(row, text="KEEP", width=12, foreground="#18794e").pack(side="left")
                    ttk.Label(row, text=str(path), wraplength=680).pack(side="left", fill="x", expand=True)
                else:
                    checked = tk.BooleanVar(value=True)
                    self.removals[path] = checked
                    ttk.Checkbutton(row, variable=checked, text="Remove").pack(side="left")
                    ttk.Label(row, text=str(path), wraplength=680).pack(side="left", fill="x", expand=True)
        self.clean_button.configure(state="normal" if self.removals else "disabled")
        recoverable = sum(group.size * (len(group.files) - 1) for group in groups)
        self.status.set(f"Scanned {count:,} files · {len(groups)} groups · {recoverable:,} bytes potentially recoverable")
        self.canvas.yview_moveto(0)

    def clean(self) -> None:
        selected = {path for path, variable in self.removals.items() if variable.get()}
        if not selected:
            messagebox.showinfo("Nothing selected", "Select at least one duplicate to remove.")
            return
        bytes_to_free = sum(path.stat().st_size for path in selected if path.exists())
        confirmed = messagebox.askyesno(
            "Confirm cleanup",
            f"Move {len(selected)} selected duplicate file(s) to the Recycle Bin?\n"
            f"Approximately {bytes_to_free:,} bytes will be freed. One copy per group will be kept.",
            icon="warning",
        )
        if not confirmed:
            return
        try:
            result = clean_duplicates(
                self.groups,
                delete=True,
                confirmed=True,
                selected_removals=selected,
                manifest_path=Path.cwd() / "dupe-sweep-undo.json",
            )
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("Cleanup failed", str(error))
            return
        messagebox.showinfo(
            "Cleanup complete",
            f"Moved {result.files_removed} file(s) to the Recycle Bin.\nUndo manifest: {result.manifest}",
        )
        self.status.set(f"Moved {result.files_removed} file(s); manifest saved to {result.manifest}")
        self.scan()


def main() -> None:
    """Launch the Tkinter application."""
    root = tk.Tk()
    DupeSweepApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
