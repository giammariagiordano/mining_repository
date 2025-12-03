# smell_ai_runner.py

import os
import sys
import glob
import tempfile
import shutil
import subprocess
import pandas as pd
from collections import Counter
from typing import Dict, Any, Optional, List


# ML-specific code smell types detected by smell_ai
ML_SMELL_TYPES = [
    "broadcasting_feature_not_used",
    "columns_and_datatype_not_explicitly_set",
    "deterministic_algorithm_option_not_used",
    "empty_column_misinitialization",
    "hyperparameters_not_explicitly_set",
    "in_place_apis_misused",
    "memory_not_freed",
    "merge_api_parameter_not_explicitly_set",
    "nan_equivalence_comparison_misused",
    "unnecessary_iteration",
    "chain_indexing",
    "dataframe_conversion_api_misused",
    "gradients_not_cleared",
    "matrix_multiplication_api_misused",
    "pytorch_call_method_misused",
    "tensor_array_not_used",
]


# ---------------------------------------------------------------------------
# CSV-safe helpers
# ---------------------------------------------------------------------------

def _sanitize_for_csv(value: Any) -> str:
    """
    Sanitize a value so that it is safe to place inside a single CSV cell
    without needing quoting/escaping.

    - Converts to string
    - Removes newlines and carriage returns
    - Removes commas and semicolons (common CSV delimiters)
    - Replaces double quotes with single quotes
    - Collapses multiple spaces
    """
    if value is None:
        return ""
    text = str(value)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace(",", " ")
    text = text.replace(";", " ")
    text = text.replace('"', "'")

    # Collapse multiple spaces
    text = " ".join(text.split())
    return text.strip()


def _format_mlsmell_record(
    filename: str,
    function_name: str,
    smell_name: str,
    message: str
) -> str:
    """
    Format a single ML smell record as plain free text, already sanitized
    for safe use inside a CSV cell.
    """
    return (
        "filename=" + _sanitize_for_csv(filename) +
        " function=" + _sanitize_for_csv(function_name) +
        " smell_name=" + _sanitize_for_csv(smell_name) +
        " message=" + _sanitize_for_csv(message)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_smell_ai_and_collect_smells(
    project_path: str,
    smell_ai_path: str = "./smell_ai",
    timeout: int = 600
) -> Dict[str, Any]:
    """
    Runs smell_ai on project_path and returns a dict with ML smell metrics.
    
    Args:
        project_path: Path to the project to analyze
        smell_ai_path: Path to the smell_ai tool directory (optional)
        timeout: Timeout in seconds for the analysis
    
    Returns:
        Dictionary with metrics:
        - mlsmell_total: Total number of ML-specific smells
        - mlsmell_<smell_type>: Count for each smell type
        - mlsmell_files: space-separated list of files with ML smells (CSV-safe)
        - mlsmell_details: single free-text string with full details, records
                           separated by " /// ". Se vale 0 significa che
                           non ci sono dettagli / nessuno smell rilevato.
    """
    metrics: Dict[str, Any] = {
        "mlsmell_total": 0,
        "mlsmell_files": "",   # List of files with ML smells (CSV-safe)
        "mlsmell_details": 0,  # Deve essere 0 quando non ci sono dettagli
    }
    
    # Initialize counters for each known smell type
    for smell_type in ML_SMELL_TYPES:
        metrics[f"mlsmell_{smell_type}"] = 0
    
    # Resolve the smell_ai_path
    if not smell_ai_path:
        smell_ai_path = "./smell_ai"
        
    # If path is relative, try to resolve it relative to the repository root
    if not os.path.isabs(smell_ai_path):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        possible_path = os.path.join(repo_root, smell_ai_path)
        if os.path.isdir(possible_path):
            smell_ai_path = possible_path
        elif os.path.isdir(os.path.abspath(smell_ai_path)):
            smell_ai_path = os.path.abspath(smell_ai_path)

    # Final check: if still not a valid directory, warn and skip
    if not os.path.isdir(smell_ai_path):
        print(f"  [CodeSmile] WARNING: smell_ai_path '{smell_ai_path}' does not exist. Skipping analysis.")
        return metrics
    
    # Create temporary output directory
    out_dir = tempfile.mkdtemp(prefix="smell_ai_")
    
    try:
        # Construct CLI command using the current Python interpreter (venv)
        cmd = [
            sys.executable, "-m", "cli.cli_runner",
            "--input", project_path,
            "--output", out_dir
        ]
        
        try:
            # Add smell_ai_path to PYTHONPATH to ensure imports work
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{smell_ai_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
            
            subprocess.run(
                cmd,
                check=True,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=smell_ai_path,
                env=env
            )
            
            # For single project analysis, results are saved in overview.csv
            overview_path = os.path.join(out_dir, "output", "overview.csv")
            
            smells_df = pd.DataFrame()
            
            if os.path.exists(overview_path):
                try:
                    smells_df = pd.read_csv(overview_path)
                except Exception as e:
                    print(f"  [CodeSmile] ERROR reading overview.csv: {e}")
            else:
                # Fallback to project_details if overview.csv is missing
                project_details_dir = os.path.join(out_dir, "output", "project_details")
                if os.path.exists(project_details_dir):
                    csv_files = glob.glob(os.path.join(project_details_dir, "*.csv"))
                    dfs: List[pd.DataFrame] = []
                    for csv_file in csv_files:
                        try:
                            df = pd.read_csv(csv_file)
                            if not df.empty:
                                dfs.append(df)
                        except Exception:
                            pass
                    if dfs:
                        smells_df = pd.concat(dfs, ignore_index=True)
            
            # No smells found → keep defaults (including mlsmell_details = 0)
            if smells_df.empty:
                return metrics
            
            # Count smells by type
            smell_counts: Counter = Counter()
            smell_detail_rows: List[str] = []
            files_with_smells: List[str] = []
            
            for _, row in smells_df.iterrows():
                # CSV has columns: filename, function_name, smell_name, etc.
                # Handle both smell_name and name_smell just in case
                smell_name_raw = row.get("smell_name", row.get("name_smell", ""))
                smell_name = str(smell_name_raw).strip().lower()
                filename = str(row.get("filename", ""))
                function_name = str(row.get("function_name", ""))
                message = str(row.get("message", ""))
                
                if not smell_name or smell_name == "nan":
                    continue

                # Normalize smell name (replace spaces and hyphens with underscores)
                normalized_smell = smell_name.replace(" ", "_").replace("-", "_")
                smell_counts[normalized_smell] += 1

                # Keep track of files (will sanitize later)
                if filename:
                    files_with_smells.append(filename)

                # Build detailed record (CSV-safe)
                smell_detail_rows.append(
                    _format_mlsmell_record(
                        filename=filename,
                        function_name=function_name,
                        smell_name=smell_name,
                        message=message,
                    )
                )
            
            # Update metrics
            total_smells = sum(smell_counts.values())
            metrics["mlsmell_total"] = total_smells
            
            # Update individual smell type counts
            for smell_type, count in smell_counts.items():
                metric_key = f"mlsmell_{smell_type}"
                metrics[metric_key] = count
            
            # Store detailed information as free text (no JSON),
            # records separated by " /// ". Quando non ci sono dettagli,
            # mlsmell_details rimane 0.
            if smell_detail_rows:
                metrics["mlsmell_details"] = " /// ".join(smell_detail_rows)
            else:
                metrics["mlsmell_details"] = 0
            
            # Store list of files with smells: unique, sorted, CSV-safe
            unique_files = sorted(set(files_with_smells))
            if unique_files:
                sanitized_files = [_sanitize_for_csv(f) for f in unique_files]
                # Avoid commas, use space as separator (safe for CSV)
                metrics["mlsmell_files"] = " ".join(sanitized_files)
            else:
                metrics["mlsmell_files"] = ""

            return metrics

        except subprocess.CalledProcessError as e:
            print(
                f"  [CodeSmile] ERROR (exit code {e.returncode}) for {project_path}. "
                f"stderr (partial): {e.stderr.decode(errors='ignore')[:300]}"
            )
            return metrics
        except subprocess.TimeoutExpired:
            print(f"  [CodeSmile] TIMEOUT after {timeout} seconds on {project_path}")
            return metrics
        except FileNotFoundError:
            print(f"  [CodeSmile] Python or smell_ai CLI not found at {smell_ai_path}")
            return metrics
        
    finally:
        # Clean up temporary directory
        shutil.rmtree(out_dir, ignore_errors=True)