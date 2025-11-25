# mine_commits_with_dpy.py

import argparse
from config import MiningConfig



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine Python projects with DPy, Bandit, and Vulture.")

    parser.add_argument("--input-csv", required=True, help="Input CSV with at least a 'ProjectName' column.")
    parser.add_argument("--output-csv", required=True, help="Output CSV to write mining results.")
    parser.add_argument("--repos-dir", required=True, help="Directory where repositories will be cloned/updated.")
    parser.add_argument("--dpy-binary", required=True, help="Path to the DPy binary.")

    parser.add_argument(
        "--max-commits",
        type=int,
        default=0,
        help="Maximum number of commits or tags per project (0 = all).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of parallel processes.",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub token (optional). If omitted, GITHUB_TOKEN env var is used if present.",
    )

    parser.add_argument(
        "--mode",
        choices=["commits", "releases", "version"],
        default="commits",
        help="Analysis mode: commits, releases (tags), or version (single ref).",
    )
    parser.add_argument(
        "--tag-pattern",
        default=None,
        help="Tag name pattern (used only in 'releases' mode). If omitted, all tags are considered.",
    )
    parser.add_argument(
        "--ref",
        dest="single_ref",
        default=None,
        help="Single ref (tag/branch/SHA) for 'version' mode.",
    )

    parser.add_argument(
        "--bandit-binary",
        default=None,
        help="Bandit command or path (optional), e.g. 'bandit'.",
    )
    parser.add_argument(
        "--vulture-binary",
        type=str,
        default=None,
        help="Vulture command or path (optional), e.g. 'vulture'.",
    )

    parser.add_argument(
        "--max-time",
        type=int,
        default=0,
        help="Max time per project in minutes (0 = no limit).",
    )

    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch the Textual TUI.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    github_token = args.github_token or None

    if args.tui:
        try:
            from tui_app import MiningTUI
            app = MiningTUI()
            app.run()
        except ImportError:
            print("Error: 'textual' is not installed. Please install it to use the TUI.")
            exit(1)
        return

    cfg = MiningConfig(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        repos_dir=args.repos_dir,
        dpy_binary=args.dpy_binary,
        max_commits=args.max_commits,
        github_token=github_token,
        jobs=args.jobs,
        analysis_mode=args.mode,
        tag_pattern=args.tag_pattern,
        single_ref=args.single_ref,
        bandit_binary=args.bandit_binary,
        vulture_binary=args.vulture_binary,
        max_project_time_minutes=args.max_time,
    )

    from core.engine import MiningEngine
    engine = MiningEngine(cfg)
    engine.run()


if __name__ == "__main__":
    main()