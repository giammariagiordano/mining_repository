# Repository Mining and Analysis Tool


This repository provides a comprehensive tool for mining and analyzing Python software repositories. It collects metrics related to code smells, vulnerabilities, dead code, and commit history, saving the results to a structured CSV file. The tool is designed to be flexible, supporting analysis over commit history, tagged releases, or a single specific version.

It includes both a command-line interface (CLI) for automation and a graphical user interface (GUI) for ease of use.

## Features

*   **Multi-Faceted Analysis**: Gathers data on code smells, security vulnerabilities, and dead code.
*   **Integration with External Tools**:
    *   **DPy**: Detects a wide range of implementation and design code smells.
    *   **Bandit**: Scans for common security vulnerabilities in Python code.
    *   **Vulture**: Finds unused (dead) code.
*   **Flexible Analysis Modes**:
    *   **`commits`**: Analyzes the repository commit-by-commit on the default branch.
    *   **`releases`**: Analyzes each tagged release.
    *   **`version`**: Analyzes a single specified commit, branch, or tag.
*   **Rich Metrics Collection**:
    *   Repository metadata (stars, forks, contributor count).
    *   Commit statistics (churn, files changed, insertions, deletions).
    *   Lines of Code (LOC) calculation.
*   **Advanced Heuristics**:
    *   Detects "fixing commits" based on commit messages.
    *   (In `commits` mode) Implements an SZZ-like algorithm to identify potential bug-introducing commits.
*   **Efficient and Resilient**:
    *   Supports parallel processing to analyze multiple repositories concurrently.
    *   Uses checkpointing to resume analysis from the last successfully processed commit/tag, making it resilient to interruptions.
*   **Dual Interface**:
    *   `mine_commits_with_dpy.py`: A powerful CLI for scripting and automation.
    *   `gui_app.py`: A user-friendly GUI built with Tkinter.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/giammariagiordano/mining_repository.git
    cd mining_repository
    ```

2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Required External Tools:**
    *   **DPy**: This tool is required. You must provide the path to its executable binary.
    *   **Bandit (Optional)**: To enable vulnerability scanning, install Bandit:
        ```bash
        pip install bandit
        ```
    *   **Vulture (Optional)**: To enable dead code analysis, install Vulture:
        ```bash
        pip install vulture
        ```

## Usage

The primary input for the tool is a CSV file containing a `ProjectName` column, where each entry is a GitHub repository in the format `owner/repo` (e.g., `psf/requests`).

### Command-Line Interface (CLI)

The CLI script `mine_commits_with_dpy.py` is the main entry point for automated analysis.

**Basic Usage:**
```bash
python mine_commits_with_dpy.py \
    --input-csv path/to/your/projects.csv \
    --output-csv path/to/your/results.csv \
    --repos-dir path/to/clone/repos \
    --dpy-binary path/to/your/DPy
```

**Example with All Features:**
This example runs the analysis in `commits` mode on 2 parallel jobs, enabling Bandit and Vulture.
```bash
python mine_commits_with_dpy.py \
    --input-csv projects.csv \
    --output-csv results.csv \
    --repos-dir ./repos \
    --dpy-binary ./DPy \
    --jobs 2 \
    --mode commits \
    --github-token "your_github_token_here" \
    --bandit-binary "bandit" \
    --vulture-binary "vulture"
```

**Analyzing Releases:**
To analyze tagged releases matching a pattern (e.g., `v*`):
```bash
python mine_commits_with_dpy.py \
    --input-csv projects.csv \
    --output-csv release_results.csv \
    --repos-dir ./repos \
    --dpy-binary ./DPy \
    --mode releases \
    --tag-pattern "v*"
```

**Analyzing a Single Version:**
To analyze a specific tag (e.g., `v2.32.0`):
```bash
python mine_commits_with_dpy.py \
    --input-csv projects.csv \
    --output-csv single_version_results.csv \
    --repos-dir ./repos \
    --dpy-binary ./DPy \
    --mode version \
    --ref "v2.32.0"
```

### Graphical User Interface (GUI)

For interactive use, you can launch the GUI.

```bash
python gui_app.py
```

The GUI provides fields for all configuration options available in the CLI. Simply fill in the paths and options, select the analysis mode, and click "Start Mining". Logs will be displayed in real-time in the text area.

## Output CSV Format

The tool generates a CSV file with a rich set of metrics for each analyzed commit or tag. Key columns include:

| Column                          | Description                                                                         |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| `project_name`                  | The name of the repository (e.g., `owner/repo`).                                    |
| `commit_sha`                    | The SHA hash of the analyzed commit.                                                |
| `commit_date`                   | The timestamp of the commit.                                                        |
| `author_name`                   | The name of the commit author.                                                      |
| `ref_type`                      | Type of reference analyzed (`commit`, `tag`, `version`).                            |
| `ref_name`                      | Name of the reference (SHA, tag name, etc.).                                        |
| `repo_stars`, `repo_forks`      | Star and fork counts from GitHub.                                                   |
| `repo_loc`                      | Total lines of code at the time of the commit/tag.                                  |
| `commit_churn`                  | Total lines added and deleted in the commit.                                        |
| `impl_smells_total`             | Total number of implementation smells detected by DPy.                              |
| `design_smells_total`           | Total number of design smells detected by DPy.                                      |
| `impl_smell_*`                  | Columns for counts of specific implementation smells (e.g., `impl_smell_long_method`). |
| `design_smell_*`                | Columns for counts of specific design smells (e.g., `design_smell_feature_envy`).   |
| `vuln_bandit_issues_total`      | Total number of vulnerabilities found by Bandit.                                    |
| `vuln_bandit_issues_*`          | Counts of vulnerabilities by severity (low, medium, high).                           |
| `deadcode_items_total`          | Total number of dead code items found by Vulture.                                   |
| `deadcode_items_*`              | Counts of dead code items by type (function, class, etc.).                          |
| `fix_commit`                    | `1` if the commit is heuristically identified as a fixing commit, otherwise `0`.       |
| `szz_introducing_commits_count` | (In `commits` mode) Number of commits identified by SZZ as introducing the fixed bug. |

## Project Structure

*   `miner.py`: Contains the core mining logic, including orchestration of different analysis modes and metric collection.
*   `mine_commits_with_dpy.py`: The command-line interface (CLI) for the tool.
*   `gui_app.py`: The Tkinter-based graphical user interface (GUI).
*   `dpy_runner.py`: Wrapper for executing the DPy tool and parsing its JSON output.
*   `bandit_runner.py`: Wrapper for running Bandit and collecting vulnerability metrics.
*   `deadcode_runner.py`: Wrapper for running Vulture and collecting dead code metrics. It supports both modern (JSON) and legacy (text) output formats from Vulture.
*   `git_utils.py`: Utility functions for interacting with Git repositories (cloning, checking out, listing tags).
*   `github_api.py`: A robust client for fetching repository statistics from the GitHub REST API, with built-in rate limit handling.
*   `config.py`: Defines the `MiningConfig` dataclass used for passing configuration throughout the application.
*   `smells.py`: Defines constants for DPy smell names and their corresponding output column names.
*   `requirements.txt`: A list of the Python packages required to run the tool.
