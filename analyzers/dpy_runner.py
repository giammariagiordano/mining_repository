import os
import glob
import tempfile
import shutil
import subprocess
import json
import re
from collections import Counter

from models.smells import (
    IMPLEMENTATION_SMELLS,
    IMPL_SMELL_TO_COL,
    DESIGN_SMELLS,
    DESIGN_SMELL_TO_COL,
)

# Caratteri considerati "pericolosi" o rumorosi per un CSV non quotato
# - newline / carriage return
# - virgole, punti e virgola
# - doppi apici
# - backslash, slash
# - parentesi quadre e graffe
# - due punti
_UNSAFE_CHARS_PATTERN = re.compile(r'[\n\r,;"\\/\[\]\{\}:]')

# Limite massimo di caratteri per il campo Details di ogni singolo smell
MAX_DETAILS_LEN = 200

# Limite massimo di caratteri per il campo aggregato "smell_details"
MAX_SMELL_DETAILS_FIELD_LEN = 5000


def _sanitize_for_csv(value) -> str:
    """
    Sanitize a value so that it is safe to place inside a single CSV cell
    without needing quoting/escaping.

    - Converte in stringa
    - Rimuove newline, carriage return
    - Rimuove virgole, punti e virgola
    - Rimuove doppi apici, backslash, slash
    - Rimuove parentesi quadre e graffe, due punti
    - Collassa spazi multipli
    """
    if value is None:
        return ""
    text = str(value)

    # Rimuove tutti i caratteri "pericolosi" o rumorosi
    text = _UNSAFE_CHARS_PATTERN.sub(" ", text)

    # Collassa spazi multipli e trim
    text = " ".join(text.split())
    return text.strip()


def _format_smell_record(smell: dict) -> str:
    """
    Format a single smell record as plain free text, already sanitized
    for safe use inside a CSV cell.
    """
    smell_name = _sanitize_for_csv(smell.get("Smell", ""))
    package = _sanitize_for_csv(smell.get("Package", ""))
    module = _sanitize_for_csv(smell.get("Module", ""))
    clazz = _sanitize_for_csv(smell.get("Class", ""))
    function = _sanitize_for_csv(smell.get("Function/Method", ""))
    line_no = _sanitize_for_csv(smell.get("Line no", ""))
    file_path = _sanitize_for_csv(smell.get("File", ""))
    details = _sanitize_for_csv(smell.get("Details", ""))

    # Troncamento opzionale per evitare lunghi blob di testo
    if len(details) > MAX_DETAILS_LEN:
        details = details[: MAX_DETAILS_LEN - 3] + "..."

    # Formato semplice e lineare, niente JSON, niente array
    return (
        "Smell=" + smell_name +
        " Package=" + package +
        " Module=" + module +
        " Class=" + clazz +
        " Function=" + function +
        " Line=" + line_no +
        " File=" + file_path +
        " Details=" + details
    )


def run_dpy_and_collect_smells(
    project_path: str,
    dpy_binary: str = "./DPy",
    timeout: int = 600
) -> dict:
    """
    Runs DPy on project_path and returns a dict with smell metrics.

    The returned dict contains:
      - 'impl_smells_total'
      - 'design_smells_total'
      - one entry for each implementation smell column (IMPL_SMELL_TO_COL values)
      - one entry for each design smell column (DESIGN_SMELL_TO_COL values)
      - 'smell_details': a single plain-text string with all smell details,
        già sanitizzato per l'uso in una cella CSV (niente JSON, niente array,
        niente slash/backslash, niente virgole) e con righe deduplicate.
    """
    # Initialize metrics with zeros for all known smell columns
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
            result = subprocess.run(
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

        # Locate JSON files produced by DPy
        impl_files = glob.glob(os.path.join(out_dir, "*implementation_smells.json"))
        design_files = glob.glob(os.path.join(out_dir, "*design_smells.json"))

        def load_all(paths):
            items = []
            for p in paths:
                try:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f)
                        # Ogni JSON può essere una lista di smells o un singolo oggetto
                        if isinstance(data, list):
                            items.extend(data)
                        else:
                            items.append(data)
                except Exception as e:
                    print(f"    [DPy] Problem reading {p}: {e}")
            return items

        impl_smells = load_all(impl_files)
        design_smells = load_all(design_files)

        # Count smells by name (only those we know about)
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

        # Collect all smell details as plain text (implementation + design)
        smell_detail_rows = []

        for s in impl_smells:
            name = s.get("Smell", "")
            if name in IMPLEMENTATION_SMELLS:
                smell_detail_rows.append(_format_smell_record(s))

        for s in design_smells:
            name = s.get("Smell", "")
            if name in DESIGN_SMELLS:
                smell_detail_rows.append(_format_smell_record(s))

        # Fill metrics for implementation smells
        impl_total = 0
        for smell_name, count in impl_counts.items():
            col = IMPL_SMELL_TO_COL.get(smell_name)
            if col is None:
                continue
            metrics[col] = count
            impl_total += count

        # Fill metrics for design smells
        design_total = 0
        for smell_name, count in design_counts.items():
            col = DESIGN_SMELL_TO_COL.get(smell_name)
            if col is None:
                continue
            metrics[col] = count
            design_total += count

        metrics["impl_smells_total"] = impl_total
        metrics["design_smells_total"] = design_total

        # Remove duplicate smell-detail rows while preserving order
        unique_smell_detail_rows = []
        seen = set()
        for row in smell_detail_rows:
            if row not in seen:
                unique_smell_detail_rows.append(row)
                seen.add(row)

        # Join all smell details into a single free-text field.
        # Separator scelto senza slash/backslash, per evitare problemi:
        # " ||| " non è un delimitatore CSV tipico.
        all_details = " ||| ".join(unique_smell_detail_rows)

        # Troncamento del campo globale per evitare CSV giganteschi
        if len(all_details) > MAX_SMELL_DETAILS_FIELD_LEN:
            all_details = all_details[: MAX_SMELL_DETAILS_FIELD_LEN - 3] + "..."

        metrics["smell_details"] = all_details

        return metrics

    finally:
        # Always clean up the temporary output directory
        shutil.rmtree(out_dir, ignore_errors=True)