# gui_app.py

import os
import sys
import threading
import ctypes
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

from config import MiningConfig



ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"


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


class MiningGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("PyLiME - Python Library Mining Engine")
        self.geometry("900x800")
        
        # Load and set logo
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "img", "pyLime.png")
            logo_image = Image.open(logo_path)
            # Resize logo to fit window icon
            logo_image = logo_image.resize((64, 64), Image.Resampling.LANCZOS)
            self.logo_photo = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(64, 64))
            
            # Set window icon (for taskbar)
            self.iconphoto(True, tk.PhotoImage(file=logo_path))
        except Exception as e:
            print(f"Could not load logo: {e}")
            self.logo_photo = None

        self.mining_thread = None

        # Main container
        main_container = ctk.CTkFrame(self)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header with logo
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 20))
        
        if self.logo_photo:
            logo_label = ctk.CTkLabel(header_frame, image=self.logo_photo, text="")
            logo_label.pack(side=tk.LEFT, padx=(0, 15))
        
        title_label = ctk.CTkLabel(
            header_frame, 
            text="PyLiME", 
            font=("Arial", 28, "bold")
        )
        title_label.pack(side=tk.LEFT)
        
        subtitle_label = ctk.CTkLabel(
            header_frame, 
            text="Python Library Mining Engine", 
            font=("Arial", 14),
            text_color="gray"
        )
        subtitle_label.pack(side=tk.LEFT, padx=(10, 0))

        self._build_form(main_container)
        self._build_log_area(main_container)

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_form(self, parent_frame):
        form_frame = ctk.CTkScrollableFrame(parent_frame, label_text="Configuration")
        form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.form_frame = form_frame
        self.form_frame.grid_columnconfigure(1, weight=1)

        row = 0

        # Input CSV
        ctk.CTkLabel(self.form_frame, text="Input CSV:").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.input_csv_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.input_csv_var).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(self.form_frame, text="Browse", command=self.browse_input_csv, width=100).grid(row=row, column=2, padx=10, pady=5)
        row += 1

        # Output CSV
        ctk.CTkLabel(self.form_frame, text="Output CSV:").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.output_csv_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.output_csv_var).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(self.form_frame, text="Browse", command=self.browse_output_csv, width=100).grid(row=row, column=2, padx=10, pady=5)
        row += 1

        # Repos dir
        ctk.CTkLabel(self.form_frame, text="Repos dir:").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.repos_dir_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.repos_dir_var).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(self.form_frame, text="Browse", command=self.browse_repos_dir, width=100).grid(row=row, column=2, padx=10, pady=5)
        row += 1

        # DPy binary
        ctk.CTkLabel(self.form_frame, text="DPy binary:").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.dpy_binary_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.dpy_binary_var).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(self.form_frame, text="Browse", command=self.browse_dpy_binary, width=100).grid(row=row, column=2, padx=10, pady=5)
        row += 1

        # Max commits
        ctk.CTkLabel(self.form_frame, text="Max commits (0 = all):").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.max_commits_var = tk.StringVar(value="0")
        ctk.CTkEntry(self.form_frame, textvariable=self.max_commits_var, width=100).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # Analysis mode
        ctk.CTkLabel(self.form_frame, text="Analysis mode:").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.analysis_mode_var = tk.StringVar(value="commits")
        mode_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        mode_frame.grid(row=row, column=1, sticky="w", padx=10, pady=5)

        ctk.CTkRadioButton(mode_frame, text="Commits", variable=self.analysis_mode_var, value="commits", command=self._on_mode_changed).pack(side=tk.LEFT, padx=(0, 10))
        ctk.CTkRadioButton(mode_frame, text="Releases (tags)", variable=self.analysis_mode_var, value="releases", command=self._on_mode_changed).pack(side=tk.LEFT, padx=(0, 10))
        ctk.CTkRadioButton(mode_frame, text="Single version", variable=self.analysis_mode_var, value="version", command=self._on_mode_changed).pack(side=tk.LEFT)
        row += 1

        # Tag pattern (for releases)
        self.tag_pattern_label = ctk.CTkLabel(self.form_frame, text="Tag pattern (releases):")
        self.tag_pattern_label.grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.tag_pattern_var = tk.StringVar()
        self.tag_pattern_entry = ctk.CTkEntry(self.form_frame, textvariable=self.tag_pattern_var, width=200)
        self.tag_pattern_entry.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # Single ref (for version)
        self.single_ref_label = ctk.CTkLabel(self.form_frame, text="Single ref (tag/branch/SHA):")
        self.single_ref_label.grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.single_ref_var = tk.StringVar()
        self.single_ref_entry = ctk.CTkEntry(self.form_frame, textvariable=self.single_ref_var, width=200)
        self.single_ref_entry.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # Jobs
        ctk.CTkLabel(self.form_frame, text="Jobs (0 = all):").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.jobs_var = tk.StringVar(value="0")
        ctk.CTkEntry(self.form_frame, textvariable=self.jobs_var, width=100).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # Max project time
        ctk.CTkLabel(self.form_frame, text="Max time per project (min, 0 = no limit):").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.max_time_var = tk.StringVar(value="0")
        ctk.CTkEntry(self.form_frame, textvariable=self.max_time_var, width=100).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # GitHub token
        ctk.CTkLabel(self.form_frame, text="GitHub token (optional):").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.github_token_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.github_token_var, show="*").grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        row += 1

        # Bandit command
        ctk.CTkLabel(self.form_frame, text="Bandit command (optional):").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.bandit_binary_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.bandit_binary_var).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        row += 1

        # Vulture command
        ctk.CTkLabel(self.form_frame, text="Vulture command (optional):").grid(row=row, column=0, sticky="e", padx=10, pady=5)
        self.vulture_binary_var = tk.StringVar()
        ctk.CTkEntry(self.form_frame, textvariable=self.vulture_binary_var).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        row += 1

        # Buttons
        button_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        button_frame.grid(row=row, column=1, sticky="w", padx=10, pady=20)
        
        self.start_button = ctk.CTkButton(button_frame, text="Start Mining", command=self.start_mining_thread, width=150)
        self.start_button.grid(row=0, column=0, padx=10, pady=10)

        self.stop_button = ctk.CTkButton(
            button_frame, 
            text="Stop Mining", 
            command=self.stop_mining, 
            width=150, 
            state="disabled",
            fg_color="#973327",  # Custom red color
            hover_color="#7a2820"  # Darker shade for hover
        )
        self.stop_button.grid(row=0, column=1, padx=10, pady=10)

        self._on_mode_changed()

    def _build_log_area(self, parent_frame):
        self.log_frame = ctk.CTkFrame(parent_frame)
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log_text = ctk.CTkTextbox(self.log_frame, state="disabled", font=("Consolas", 12))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Progress label
        self.progress_label = ctk.CTkLabel(self.log_frame, text="Ready to start mining", font=("Arial", 12, "bold"))
        self.progress_label.pack(fill=tk.X, padx=5, pady=(5, 0))

        # Configure tags for colors (CustomTkinter Textbox doesn't support tags exactly like Tkinter Text, 
        # but we can insert text. For simplicity, we'll just insert text. 
        # If we need colors, we might need a different approach or just use plain text).
        # Actually CTkTextbox is a wrapper around Tkinter Text, so tags might work if we access the underlying widget.
        # But for now let's keep it simple.

    # -------------------------------------------------------------------------
    # Browse helpers
    # -------------------------------------------------------------------------

    def browse_input_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.input_csv_var.set(path)

    def browse_output_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.output_csv_var.set(path)

    def browse_repos_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.repos_dir_var.set(path)

    def browse_dpy_binary(self):
        path = filedialog.askopenfilename(filetypes=[("Executable", "*"), ("All files", "*.*")])
        if path:
            self.dpy_binary_var.set(path)

    # -------------------------------------------------------------------------
    # Mode-dependent fields
    # -------------------------------------------------------------------------

    def _on_mode_changed(self):
        mode = self.analysis_mode_var.get()

        if mode == "releases":
            self.tag_pattern_entry.configure(state="normal")
            self.tag_pattern_label.configure(text_color=("black", "white"))
        else:
            self.tag_pattern_entry.configure(state="disabled")
            self.tag_pattern_label.configure(text_color="gray")

        if mode == "version":
            self.single_ref_entry.configure(state="normal")
            self.single_ref_label.configure(text_color=("black", "white"))
        else:
            self.single_ref_entry.configure(state="disabled")
            self.single_ref_label.configure(text_color="gray")

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

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress_label.configure(text="Starting mining process...")

        # Redirect stdout/stderr
        # Note: CTkTextbox doesn't fully support the same tag methods as Tkinter Text easily exposed.
        # We will use a simpler redirector that just inserts at end.
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
            raise ValueError("Please fill in all required fields (CSV paths, repos dir, DPy binary).")

        try:
            max_commits = int(self.max_commits_var.get())
        except ValueError:
            raise ValueError("Max commits must be an integer.")

        try:
            jobs = int(self.jobs_var.get())
        except ValueError:
            raise ValueError("Jobs must be an integer.")

        try:
            max_time = int(self.max_time_var.get())
        except ValueError:
            raise ValueError("Max time per project must be an integer.")

        github_token = self.github_token_var.get().strip() or None
        if github_token is None:
            github_token = os.environ.get("GITHUB_TOKEN")

        analysis_mode = self.analysis_mode_var.get().strip() or "commits"
        tag_pattern = self.tag_pattern_var.get().strip() or None
        single_ref = self.single_ref_var.get().strip() or None

        bandit_binary = self.bandit_binary_var.get().strip() or None
        vulture_binary = self.vulture_binary_var.get().strip() or None

        if analysis_mode == "releases" and not tag_pattern:
            print("[GUI] WARNING: 'Releases' mode selected but no tag pattern provided. All tags will be considered.")

        if analysis_mode == "version" and not single_ref:
            raise ValueError("Single-version analysis requires a ref (tag/branch/SHA) in the 'Single ref' field.")

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
            max_project_time_minutes=max_time,
        )
        return cfg

    def _run_mining_safe(self, cfg: MiningConfig):
        try:
            from core.engine import MiningEngine
            
            def progress_callback(completed, total):
                # Update progress label from worker thread
                self.after(0, self._update_progress, completed, total)
            
            engine = MiningEngine(cfg, progress_callback=progress_callback)
            engine.run()
        except Exception as e:
            print(f"[GUI] ERROR during mining: {e}")
        finally:
            # We need to schedule the button update on the main thread
            self.after(0, self._reset_buttons)
            self.mining_thread = None

    def _update_progress(self, completed, total):
        """Update the progress label with current status"""
        remaining = total - completed
        self.progress_label.configure(
            text=f"Progress: {completed}/{total} projects completed ({remaining} remaining)"
        )

    def _reset_buttons(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.progress_label.configure(text="Mining completed!")



def main():
    app = MiningGUI()
    app.mainloop()


if __name__ == "__main__":
    main()