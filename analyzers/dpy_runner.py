# dpy_runner.py

import os
import glob
import json
import tempfile
import shutil
import subprocess
from collections import Counter

from models.smells import (
    IMPLEMENTATION_SMELLS,
    IMPL_SMELL_TO_COL,
    DESIGN_SMELLS,
    DESIGN_SMELL_TO_COL,
)


def run_dpy_and_collect_smells(project_path: str,
                               dpy_binary: str = "./DPy",
                               timeout: int = 600) -> dict:
    """
    Runs DPy on project_path and returns a dict with smell metrics.
    """
    metrics = {
        "impl_smells_total": 0,
        "design_smells_total": 0,
    }
    for col in IMPL_SMELL_TO_COL.values():
        metrics[col] = 0
    for col in DESIGN_SMELL_TO_COL.values():
        metrics[col] = 0

    out_dir = tempfile.mkdtemp(prefix="dpy_")

    try:
        cmd = [dpy_binary, "analyze", "--input", project_path, "--output", out_dir]
        try:
            subprocess.run(
                cmd,
                check=True,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            print(
                f"  [DPy] ERROR (exit code {e.returncode}) for {project_path}. "
                f"stderr (partial): {e.stderr.decode(errors='ignore')[:300]}"
            )
            return metrics
        except subprocess.TimeoutExpired:
            print(f"  [DPy] TIMEOUT after {timeout} seconds on {project_path}")
            return metrics

        impl_files = glob.glob(os.path.join(out_dir, "*implementation_smells.json"))
        design_files = glob.glob(os.path.join(out_dir, "*design_smells.json"))

        def load_all(paths):
            items = []
            for p in paths:
                try:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            items.extend(data)
                        else:
                            items.append(data)
                except Exception as e:
                    print(f"    [DPy] Problem reading {p}: {e}")
            return items

        impl_smells = load_all(impl_files)
        design_smells = load_all(design_files)

        impl_counts = Counter()
        for s in impl_smells:
            name = s.get("Smell", "")
            if name in IMPLEMENTATION_SMELLS:
                impl_counts[name] += 1

        design_counts = Counter()
        for s in design_smells:
            name = s.get("Smell", "")
            if name in DESIGN_SMELLS:
                design_counts[name] += 1

        smell_details = []

        impl_total = 0
        for s in impl_smells:
            name = s.get("Smell", "")
            if name in IMPLEMENTATION_SMELLS:
                smell_details.append({
                    "Smell": name,
                    "Package": s.get("Package", ""),
                    "Module": s.get("Module", ""),
                    "Class": s.get("Class", ""),
                    "Function/Method": s.get("Function/Method", ""),
                    "Line no": s.get("Line no", ""),
                    "File": s.get("File", ""),
                    "Details": s.get("Details", "")
                })

        for smell_name, count in impl_counts.items():
            col = IMPL_SMELL_TO_COL.get(smell_name)
            if col is None:
                continue
            metrics[col] = count
            impl_total += count

        design_total = 0
        for s in design_smells:
            name = s.get("Smell", "")
            if name in DESIGN_SMELLS:
                smell_details.append({
                    "Smell": name,
                    "Package": s.get("Package", ""),
                    "Module": s.get("Module", ""),
                    "Class": s.get("Class", ""),
                    "Function/Method": s.get("Function/Method", ""),
                    "Line no": s.get("Line no", ""),
                    "File": s.get("File", ""),
                    "Details": s.get("Details", "")
                })

        for smell_name, count in design_counts.items():
            col = DESIGN_SMELL_TO_COL.get(smell_name)
            if col is None:
                continue
            metrics[col] = count
            design_total += count

        metrics["impl_smells_total"] = impl_total
        metrics["design_smells_total"] = design_total
        metrics["smell_details"] = json.dumps(smell_details)
        return metrics

    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
