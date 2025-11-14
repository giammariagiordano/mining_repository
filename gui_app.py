# gui_app.py

import os
import sys
import threading
import ctypes

import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox

from config import MiningConfig
from miner import run_mining


class TextRedirector:
    """
    Redirects stdout/stderr to a Tkinter Text widget.
    """

    def __init__(self, text_widget, tag="stdout"):
        self.text_widget = text_widget
        self.tag = tag

    def write(self, s):
        self.text_widget.configure(state="normal")
        self.text_widget.insert(tk.END, s, (self.tag,))
        self.text_widget.see(tk.END)
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


def _async_raise(tid, exctype):
    """
    Raise an exception in the thread with id 'tid'.
    Uses CPython internal API PyThreadState_SetAsyncExc.
    """
    if not tid:
        return
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(tid), ctypes.py_object(exctype)
    )
    if res == 0:
        raise ValueError("Invalid thread id")
    elif res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), 0)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class MiningGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DPy Mining Tool")
        self.geometry("950x700")

        self.mining_thread = None

        self._build_form()
        self._build_log_area()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_form(self):
        frm = tk.Frame(self)
        frm.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        row = 0

        # Input CSV
        tk.Label(frm, text="Input CSV:").grid(row=row, column=0, sticky="e")
        self.input_csv_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.input_csv_var, width=70).grid(
            row=row, column=1, sticky="w"
        )
        tk.Button(frm, text="Browse", command=self.browse_input_csv).grid(
            row=row, column=2, padx=5
        )
        row += 1

        # Output CSV
        tk.Label(frm, text="Output CSV:").grid(row=row, column=0, sticky="e")
        self.output_csv_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.output_csv_var, width=70).grid(
            row=row, column=1, sticky="w"
        )
        tk.Button(frm, text="Browse", command=self.browse_output_csv).grid(
            row=row, column=2, padx=5
        )
        row += 1

        # Repos dir
        tk.Label(frm, text="Repos dir:").grid(row=row, column=0, sticky="e")
        self.repos_dir_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.repos_dir_var, width=70).grid(
            row=row, column=1, sticky="w"
        )
        tk.Button(frm, text="Browse", command=self.browse_repos_dir).grid(
            row=row, column=2, padx=5
        )
        row += 1

        # DPy binary
        tk.Label(frm, text="DPy binary:").grid(row=row, column=0, sticky="e")
        self.dpy_binary_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.dpy_binary_var, width=70).grid(
            row=row, column=1, sticky="w"
        )
        tk.Button(frm, text="Browse", command=self.browse_dpy_binary).grid(
            row=row, column=2, padx=5
        )
        row += 1

        # Max commits
        tk.Label(frm, text="Max commits (0 = all):").grid(
            row=row, column=0, sticky="e"
        )
        self.max_commits_var = tk.StringVar(value="0")
        tk.Entry(frm, textvariable=self.max_commits_var, width=10).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        # Analysis mode
        tk.Label(frm, text="Analysis mode:").grid(row=row, column=0, sticky="e")
        self.analysis_mode_var = tk.StringVar(value="commits")
        mode_frame = tk.Frame(frm)
        mode_frame.grid(row=row, column=1, sticky="w")

        tk.Radiobutton(
            mode_frame,
            text="Commits",
            variable=self.analysis_mode_var,
            value="commits",
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Radiobutton(
            mode_frame,
            text="Releases (tags)",
            variable=self.analysis_mode_var,
            value="releases",
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Radiobutton(
            mode_frame,
            text="Single version",
            variable=self.analysis_mode_var,
            value="version",
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT)
        row += 1

        # Tag pattern (for releases)
        self.tag_pattern_label = tk.Label(frm, text="Tag pattern (releases):")
        self.tag_pattern_label.grid(row=row, column=0, sticky="e")
        self.tag_pattern_var = tk.StringVar()
        self.tag_pattern_entry = tk.Entry(
            frm, textvariable=self.tag_pattern_var, width=30
        )
        self.tag_pattern_entry.grid(row=row, column=1, sticky="w")
        row += 1

        # Single ref (for version)
        self.single_ref_label = tk.Label(
            frm, text="Single ref (tag/branch/SHA):"
        )
        self.single_ref_label.grid(row=row, column=0, sticky="e")
        self.single_ref_var = tk.StringVar()
        self.single_ref_entry = tk.Entry(
            frm, textvariable=self.single_ref_var, width=30
        )
        self.single_ref_entry.grid(row=row, column=1, sticky="w")
        row += 1

        # Jobs
        tk.Label(frm, text="Jobs (processes):").grid(row=row, column=0, sticky="e")
        default_jobs = os.cpu_count() or 1
        self.jobs_var = tk.StringVar(value=str(default_jobs))
        tk.Entry(frm, textvariable=self.jobs_var, width=10).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        # GitHub token
        tk.Label(frm, text="GitHub token (optional):").grid(
            row=row, column=0, sticky="e"
        )
        self.github_token_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.github_token_var, width=70, show="*").grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        # Bandit command
        tk.Label(frm, text="Bandit command (optional):").grid(
            row=row, column=0, sticky="e"
        )
        self.bandit_binary_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.bandit_binary_var, width=70).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        # Vulture command
        tk.Label(frm, text="Vulture command (optional):").grid(
            row=row, column=0, sticky="e"
        )
        self.vulture_binary_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.vulture_binary_var, width=70).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        # Start button
        self.start_button = tk.Button(
            frm, text="Start Mining", command=self.start_mining_thread
        )
        self.start_button.grid(row=row, column=1, pady=10, sticky="w")

        # Stop button
        self.stop_button = tk.Button(
            frm, text="Stop", command=self.stop_mining, state="disabled"
        )
        self.stop_button.grid(row=row, column=2, pady=10, sticky="w")

        self._on_mode_changed()

    def _build_log_area(self):
        self.log_text = scrolledtext.ScrolledText(self, state="disabled")
        self.log_text.pack(
            side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10
        )

        self.log_text.tag_configure("stdout", foreground="black")
        self.log_text.tag_configure("stderr", foreground="red")

    # -------------------------------------------------------------------------
    # Browse helpers
    # -------------------------------------------------------------------------

    def browse_input_csv(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.input_csv_var.set(path)

    def browse_output_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.output_csv_var.set(path)

    def browse_repos_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.repos_dir_var.set(path)

    def browse_dpy_binary(self):
        path = filedialog.askopenfilename(
            filetypes=[("Executable", "*"), ("All files", "*.*")]
        )
        if path:
            self.dpy_binary_var.set(path)

    # -------------------------------------------------------------------------
    # Mode-dependent fields
    # -------------------------------------------------------------------------

    def _on_mode_changed(self):
        mode = self.analysis_mode_var.get()

        if mode == "releases":
            self.tag_pattern_entry.config(state="normal")
            self.tag_pattern_label.config(fg="black")
        else:
            self.tag_pattern_entry.config(state="disabled")
            self.tag_pattern_label.config(fg="gray")

        if mode == "version":
            self.single_ref_entry.config(state="normal")
            self.single_ref_label.config(fg="black")
        else:
            self.single_ref_entry.config(state="disabled")
            self.single_ref_label.config(fg="gray")

    # -------------------------------------------------------------------------
    # Mining control
    # -------------------------------------------------------------------------

    def start_mining_thread(self):
        if self.mining_thread is not None and self.mining_thread.is_alive():
            messagebox.showwarning("Mining in progress", "Mining is already running.")
            return

        try:
            cfg = self._build_config_from_ui()
        except ValueError as e:
            messagebox.showerror("Configuration error", str(e))
            return

        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")

        sys.stdout = TextRedirector(self.log_text, "stdout")
        sys.stderr = TextRedirector(self.log_text, "stderr")

        self.mining_thread = threading.Thread(
            target=self._run_mining_safe, args=(cfg,), daemon=True
        )
        self.mining_thread.start()

    def stop_mining(self):
        if self.mining_thread is None or not self.mining_thread.is_alive():
            messagebox.showinfo("Not running", "No mining process is currently running.")
            return

        try:
            print("[GUI] Stop requested. Sending KeyboardInterrupt to mining thread...")
            _async_raise(self.mining_thread.ident, KeyboardInterrupt)
        except Exception as e:
            print(f"[GUI] ERROR while trying to stop mining: {e}")

    def _build_config_from_ui(self) -> MiningConfig:
        input_csv = self.input_csv_var.get().strip()
        output_csv = self.output_csv_var.get().strip()
        repos_dir = self.repos_dir_var.get().strip()
        dpy_binary = self.dpy_binary_var.get().strip()

        if not input_csv or not output_csv or not repos_dir or not dpy_binary:
            raise ValueError(
                "Please fill in all required fields (CSV paths, repos dir, DPy binary)."
            )

        try:
            max_commits = int(self.max_commits_var.get())
        except ValueError:
            raise ValueError("Max commits must be an integer.")

        try:
            jobs = int(self.jobs_var.get())
        except ValueError:
            raise ValueError("Jobs must be an integer.")

        github_token = self.github_token_var.get().strip() or None
        if github_token is None:
            github_token = os.environ.get("GITHUB_TOKEN")

        analysis_mode = self.analysis_mode_var.get().strip() or "commits"
        tag_pattern = self.tag_pattern_var.get().strip() or None
        single_ref = self.single_ref_var.get().strip() or None

        bandit_binary = self.bandit_binary_var.get().strip() or None
        vulture_binary = self.vulture_binary_var.get().strip() or None

        if analysis_mode == "releases" and not tag_pattern:
            print(
                "[GUI] WARNING: 'Releases' mode selected but no tag pattern provided. "
                "All tags will be considered."
            )

        if analysis_mode == "version" and not single_ref:
            raise ValueError(
                "Single-version analysis requires a ref "
                "(tag/branch/SHA) in the 'Single ref' field."
            )

        cfg = MiningConfig(
            input_csv=input_csv,
            output_csv=output_csv,
            repos_dir=repos_dir,
            dpy_binary=dpy_binary,
            max_commits=max_commits,
            github_token=github_token,
            jobs=jobs,
            analysis_mode=analysis_mode,
            tag_pattern=tag_pattern,
            single_ref=single_ref,
            bandit_binary=bandit_binary,
            vulture_binary=vulture_binary,
        )
        return cfg

    def _run_mining_safe(self, cfg: MiningConfig):
        try:
            run_mining(cfg)
        except Exception as e:
            print(f"[GUI] ERROR during mining: {e}")
        finally:
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.mining_thread = None


def main():
    app = MiningGUI()
    app.mainloop()


if __name__ == "__main__":
    main()