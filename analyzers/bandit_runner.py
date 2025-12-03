# bandit_runner.py

import json
import subprocess
from collections import Counter
from typing import Dict, Any, Optional


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


def _format_vuln_record(item: Dict[str, Any]) -> str:
    """
    Format a single Bandit issue as plain free text, already sanitized
    for safe use inside a CSV cell.
    """
    return (
        "filename=" + _sanitize_for_csv(item.get("filename", "")) +
        " line=" + _sanitize_for_csv(item.get("line_number", "")) +
        " test_id=" + _sanitize_for_csv(item.get("test_id", "")) +
        " severity=" + _sanitize_for_csv(item.get("issue_severity", "")) +
        " confidence=" + _sanitize_for_csv(item.get("issue_confidence", "")) +
        " issue=" + _sanitize_for_csv(item.get("issue_text", ""))
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_bandit_and_collect_vulns(
    project_path: str,
    bandit_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Bandit on the given project_path (recursively) and aggregate
    vulnerability information.

    Returns a dictionary with the following keys:

      - vuln_bandit_issues_total
      - vuln_bandit_issues_low
      - vuln_bandit_issues_medium
      - vuln_bandit_issues_high
      - vuln_bandit_test_ids
      - vuln_bandit_issue_summaries
      - vuln_details

    Notes:
    - All free-text fields are pre-sanitized to avoid characters that break CSV
      (no commas, semicolons, newlines, or double quotes).
    - vuln_bandit_test_ids is a space-separated list of unique Bandit test IDs
      (e.g., "B101 B303 B608").
    - vuln_bandit_issue_summaries is una lista separata da " || " di stringhe
      nella forma "<TEST_ID>: <issue_text>", già sanificate.
    - vuln_details è un'unica stringa di testo libero con i dettagli delle
      vulnerabilità, con record separati da " /// ".
    """
    if not bandit_binary:
        # Bandit explicitly disabled
        return {}

    cmd = [
        bandit_binary,
        "-q",        # quiet (suppress progress)
        "-r",        # recursive
        project_path,
        "-f",
        "json",
    ]

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,  # Bandit returns 1 when issues are found
        )
    except FileNotFoundError:
        print(f"[BANDIT] Command not found: {bandit_binary}. Skipping Bandit analysis.")
        return {}
    except Exception as e:
        print(f"[BANDIT] Error while running Bandit: {e}")
        return {}

    # Bandit returns:
    #   - exit code 0 if no issues found
    #   - exit code 1 if issues found
    #   - other codes for errors
    if proc.returncode not in (0, 1):
        print(f"[BANDIT] Non-zero exit code {proc.returncode}. stderr:")
        print(proc.stderr)

    raw = proc.stdout or proc.stderr or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("[BANDIT] Failed to parse JSON output.")
        return {}

    results = data.get("results", [])
    if not isinstance(results, list):
        return {}

    severity_counter: Counter = Counter()
    test_ids = set()
    issue_summaries = set()
    vuln_detail_rows = []

    for item in results:
        sev = str(item.get("issue_severity", "")).upper().strip()
        if sev:
            severity_counter[sev] += 1

        test_id = str(item.get("test_id", "")).strip()
        issue_text = str(item.get("issue_text", "")).strip()

        if test_id:
            test_ids.add(test_id)
            if issue_text:
                # Compact summary "BXXX: description" (sanitized)
                summary = f"{test_id}: {issue_text}"
                issue_summaries.add(_sanitize_for_csv(summary))

        # Build a full detail record (sanitized)
        vuln_detail_rows.append(
            _format_vuln_record(
                {
                    "filename": item.get("filename", ""),
                    "line_number": item.get("line_number", ""),
                    "test_id": test_id,
                    "issue_text": issue_text,
                    "issue_severity": sev,
                    "issue_confidence": item.get("issue_confidence", ""),
                }
            )
        )

    total = sum(severity_counter.values())

    # test_ids: join with space, then sanitize (even if dovrebbe già essere ok)
    if test_ids:
        test_ids_str = _sanitize_for_csv(" ".join(sorted(test_ids)))
    else:
        test_ids_str = ""

    metrics: Dict[str, Any] = {
        "vuln_bandit_issues_total": total,
        "vuln_bandit_issues_low": severity_counter.get("LOW", 0),
        "vuln_bandit_issues_medium": severity_counter.get("MEDIUM", 0),
        "vuln_bandit_issues_high": severity_counter.get("HIGH", 0),
        "vuln_bandit_test_ids": test_ids_str,
        "vuln_bandit_issue_summaries": " || ".join(sorted(issue_summaries))
        if issue_summaries
        else "",
        # Dettagli come testo libero, record separati da " /// "
        "vuln_details": " /// ".join(vuln_detail_rows) if vuln_detail_rows else "",
    }

    return metrics