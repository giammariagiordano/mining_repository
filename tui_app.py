import os
import sys
import threading
import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Input, Label, RadioButton, RadioSet, Log, Static
from textual.binding import Binding
from textual.worker import Worker

from config import MiningConfig


class MiningTUI(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    
    .box {
        height: auto;
        border: solid green;
        margin: 1;
        padding: 1;
    }

    .label {
        width: 20;
        content-align: right middle;
    }

    .input-row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }

    Input {
        width: 1fr;
    }

    Button {
        margin-left: 1;
    }

    Log {
        height: 1fr;
        border: solid blue;
        background: $surface;
    }

    #start-btn {
        background: green;
        color: white;
    }

    #stop-btn {
        background: red;
        color: white;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with ScrollableContainer():
            with Vertical(classes="box"):
                yield Label("Configuration", classes="header")
                
                with Horizontal(classes="input-row"):
                    yield Label("Input CSV:", classes="label")
                    yield Input(placeholder="Path to input CSV", id="input_csv")
                
                with Horizontal(classes="input-row"):
                    yield Label("Output CSV:", classes="label")
                    yield Input(placeholder="Path to output CSV", id="output_csv")
                
                with Horizontal(classes="input-row"):
                    yield Label("Repos Dir:", classes="label")
                    yield Input(placeholder="Directory for repos", id="repos_dir")
                
                with Horizontal(classes="input-row"):
                    yield Label("DPy Binary:", classes="label")
                    yield Input(placeholder="Path to DPy binary", id="dpy_binary")
                
                with Horizontal(classes="input-row"):
                    yield Label("Max Commits:", classes="label")
                    yield Input(placeholder="0 for all", value="0", id="max_commits", type="integer")

                with Horizontal(classes="input-row"):
                    yield Label("Jobs (0=All):", classes="label")
                    yield Input(placeholder="0 for all cores", value="0", id="jobs", type="integer")

                with Horizontal(classes="input-row"):
                    yield Label("GitHub Token:", classes="label")
                    yield Input(placeholder="Optional", password=True, id="github_token")

            with Vertical(classes="box"):
                yield Label("Mode", classes="header")
                with RadioSet(id="mode_radios"):
                    yield RadioButton("Commits", value=True, id="mode_commits")
                    yield RadioButton("Releases", id="mode_releases")
                    yield RadioButton("Version", id="mode_version")
                
                with Horizontal(classes="input-row"):
                    yield Label("Tag Pattern:", classes="label")
                    yield Input(placeholder="For releases mode", id="tag_pattern")

                with Horizontal(classes="input-row"):
                    yield Label("Single Ref:", classes="label")
                    yield Input(placeholder="For version mode", id="single_ref")

            with Horizontal(classes="box"):
                yield Button("Start Mining", id="start-btn")
                yield Button("Stop", id="stop-btn", disabled=True)

            yield Log(id="log_area")

    def on_mount(self) -> None:
        self.title = "DPy Mining Tool TUI"
        # Pre-fill from env vars or defaults if desired
        self.query_one("#jobs", Input).value = "0"

    class RedirectStdout:
        def __init__(self, log_widget):
            self.log_widget = log_widget

        def write(self, string):
            if string.strip():
                self.log_widget.write(string)

        def flush(self):
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            self.start_mining()
        elif event.button.id == "stop-btn":
            self.stop_mining()

    def start_mining(self):
        try:
            cfg = self._build_config()
        except ValueError as e:
            self.query_one("#log_area", Log).write(f"[red]Error: {e}[/red]")
            return

        self.query_one("#start-btn", Button).disabled = True
        self.query_one("#stop-btn", Button).disabled = False
        self.query_one("#log_area", Log).clear()
        self.query_one("#log_area", Log).write("Starting mining...")

        self.run_worker(self._mining_worker(cfg), exclusive=True, thread=True)

    def stop_mining(self):
        # This is tricky with threads. We can't easily kill a thread.
        # But run_mining handles KeyboardInterrupt.
        # In a TUI, we might need a better way to signal stop.
        # For now, we'll just disable the button and hope the user knows 
        # that stopping a thread is hard.
        # Ideally, we'd use a shared flag or similar.
        self.query_one("#log_area", Log).write("[red]Stop requested (not fully implemented in TUI yet)[/red]")
        # In a real app, we'd use a threading.Event or similar to signal the miner to stop.
        # Since miner.py uses ProcessPoolExecutor, we can't easily stop it from here without
        # refactoring miner.py to check a flag.
        # But we can try to raise KeyboardInterrupt in the thread if we had the thread ID.
        pass

    def _mining_worker(self, cfg):
        # Redirect stdout/stderr to the log widget
        log_widget = self.query_one("#log_area", Log)
        
        # Capture stdout/stderr
        # Note: This might be risky in a threaded TUI, but Textual's Log is thread-safe-ish.
        # We'll just write directly to the log widget in a wrapper.
        
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        sys.stdout = self.RedirectStdout(log_widget)
        sys.stderr = self.RedirectStdout(log_widget)

        try:
            from core.engine import MiningEngine
            engine = MiningEngine(cfg)
            engine.run()
            log_widget.write("[green]Mining completed![/green]")
        except Exception as e:
            log_widget.write(f"[red]Mining failed: {e}[/red]")
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            self.call_from_thread(self._reset_buttons)

    def _reset_buttons(self):
        self.query_one("#start-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = True

    def _build_config(self) -> MiningConfig:
        input_csv = self.query_one("#input_csv", Input).value.strip()
        output_csv = self.query_one("#output_csv", Input).value.strip()
        repos_dir = self.query_one("#repos_dir", Input).value.strip()
        dpy_binary = self.query_one("#dpy_binary", Input).value.strip()

        if not input_csv or not output_csv or not repos_dir or not dpy_binary:
            raise ValueError("Please fill in all required fields.")

        max_commits = int(self.query_one("#max_commits", Input).value or 0)
        jobs = int(self.query_one("#jobs", Input).value or 0)
        github_token = self.query_one("#github_token", Input).value.strip() or None
        
        # Determine mode
        if self.query_one("#mode_commits", RadioButton).value:
            mode = "commits"
        elif self.query_one("#mode_releases", RadioButton).value:
            mode = "releases"
        else:
            mode = "version"

        tag_pattern = self.query_one("#tag_pattern", Input).value.strip() or None
        single_ref = self.query_one("#single_ref", Input).value.strip() or None

        return MiningConfig(
            input_csv=input_csv,
            output_csv=output_csv,
            repos_dir=repos_dir,
            dpy_binary=dpy_binary,
            max_commits=max_commits,
            github_token=github_token,
            jobs=jobs,
            analysis_mode=mode,
            tag_pattern=tag_pattern,
            single_ref=single_ref,
        )

if __name__ == "__main__":
    app = MiningTUI()
    app.run()
