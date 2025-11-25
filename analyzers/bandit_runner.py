# bandit_runner.py

import json
import subprocess
from collections import Counter
from typing import Dict, Any, Optional


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

    If bandit_binary is None or Bandit is not available, returns an empty dict.

    Notes:
    - vuln_bandit_test_ids is a comma-separated list of unique Bandit test IDs
      (e.g., "B101,B303,B608").
    - vuln_bandit_issue_summaries is a " || " separated list of strings in the form
      "<TEST_ID>: <issue_text>".
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

    vuln_details = []

    for item in results:
        sev = str(item.get("issue_severity", "")).upper().strip()
        if sev:
            severity_counter[sev] += 1

        test_id = str(item.get("test_id", "")).strip()
        issue_text = str(item.get("issue_text", "")).strip()

        if test_id:
            test_ids.add(test_id)
            if issue_text:
                # Compact summary "BXXX: description"
                issue_summaries.add(f"{test_id}: {issue_text}")
        
        vuln_details.append({
            "filename": item.get("filename", ""),
            "line_number": item.get("line_number", ""),
            "test_id": test_id,
            "issue_text": issue_text,
            "issue_severity": sev,
            "issue_confidence": item.get("issue_confidence", "")
        })

    total = sum(severity_counter.values())

    metrics: Dict[str, Any] = {
        "vuln_bandit_issues_total": total,
        "vuln_bandit_issues_low": severity_counter.get("LOW", 0),
        "vuln_bandit_issues_medium": severity_counter.get("MEDIUM", 0),
        "vuln_bandit_issues_high": severity_counter.get("HIGH", 0),
        "vuln_bandit_test_ids": ",".join(sorted(test_ids)) if test_ids else "",
        "vuln_bandit_issue_summaries": " || ".join(sorted(issue_summaries))
        if issue_summaries
        else "",
        "vuln_details": json.dumps(vuln_details)
    }

    return metrics