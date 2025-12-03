# deadcode_runner.py

import json
import re
import subprocess
from collections import Counter
from typing import Dict, Any, Optional, List


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


def _format_deadcode_record(item: Dict[str, Any]) -> str:
    """
    Format a single deadcode record as plain free text, already sanitized
    for safe use inside a CSV cell.
    """
    return (
        "type=" + _sanitize_for_csv(str(item.get("type", "other")).lower().strip()) +
        " name=" + _sanitize_for_csv(item.get("name", "")) +
        " filename=" + _sanitize_for_csv(item.get("filename", "")) +
        " lineno=" + _sanitize_for_csv(item.get("lineno")) +
        " confidence=" + _sanitize_for_csv(item.get("confidence"))
    )


# ---------------------------------------------------------------------------
# Common aggregation helper
# ---------------------------------------------------------------------------

def _aggregate_items(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Given a list of "items", each with at least:
      - type
      - name
      - filename
      - lineno
      - confidence

    aggregate counts per type and build summaries.
    """
    type_counter: Counter = Counter()
    summaries: List[str] = []
    detail_rows: List[str] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        itype = str(item.get("type", "other")).lower().strip()
        name = str(item.get("name", "")).strip()
        filename = str(item.get("filename", "")).strip()
        lineno = item.get("lineno", None)
        confidence = item.get("confidence", None)

        if not itype:
            itype = "other"
        type_counter[itype] += 1

        # Build compact summary string (sanitized)
        parts = [itype]
        if name:
            parts.append(name)
        loc_part = ""
        if filename:
            loc_part = filename
            if lineno is not None:
                loc_part = f"{filename}:{lineno}"
        elif lineno is not None:
            loc_part = f"line {lineno}"

        meta_parts = []
        if loc_part:
            meta_parts.append(loc_part)
        if confidence is not None:
            meta_parts.append(f"conf={confidence}")

        text = " ".join(parts)
        if meta_parts:
            text += " (" + ", ".join(meta_parts) + ")"

        summaries.append(_sanitize_for_csv(text))

        # Build full detail record (sanitized)
        detail_rows.append(
            _format_deadcode_record(
                {
                    "type": itype,
                    "name": name,
                    "filename": filename,
                    "lineno": lineno,
                    "confidence": confidence,
                }
            )
        )

    total = sum(type_counter.values())

    def count_for(t: str) -> int:
        return type_counter.get(t, 0)

    metrics: Dict[str, Any] = {
        "deadcode_items_total": total,
        "deadcode_items_function": count_for("function"),
        "deadcode_items_class": count_for("class"),
        "deadcode_items_attribute": count_for("attribute"),
        "deadcode_items_variable": count_for("variable"),
        "deadcode_items_property": count_for("property"),
    }

    known_types = {"function", "class", "attribute", "variable", "property"}
    other_count = sum(
        cnt for t, cnt in type_counter.items() if t not in known_types
    )
    metrics["deadcode_items_other"] = other_count

    # Summaries: già sanificate, unite con separatore che non rompe CSV
    metrics["deadcode_items_summaries"] = " || ".join(summaries) if summaries else ""

    # Dettagli: testo libero, già sanificato, separato da " /// "
    metrics["deadcode_details"] = " /// ".join(detail_rows) if detail_rows else ""

    return metrics


# ---------------------------------------------------------------------------
# JSON helpers (for newer Vulture versions)
# ---------------------------------------------------------------------------

def _extract_json_array(raw: str) -> Optional[str]:
    """
    Try to extract a JSON array substring from a larger string, e.g. if
    Vulture prints warnings or banners before/after the JSON.

    Returns the substring from the first '[' to the last ']' if it looks
    plausible, otherwise None.
    """
    if not raw:
        return None

    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = raw[start: end + 1].strip()
    if not candidate:
        return None

    if not (candidate.startswith("[") and candidate.endswith("]")):
        return None

    return candidate


def _run_vulture_json_mode(project_path: str, vulture_binary: str) -> Optional[Dict[str, Any]]:
    """
    Try to run Vulture with --json and aggregate the results.
    Returns metrics dict or None if JSON mode is not supported or parsing fails.
    """
    cmd = [vulture_binary, project_path, "--json"]

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,  # non-zero exit is normal when dead code found
        )
    except FileNotFoundError:
        print(f"[VULTURE] Command not found: {vulture_binary}. Skipping Vulture analysis.")
        return None
    except Exception as e:
        print(f"[VULTURE] Error while running Vulture (JSON mode): {e}")
        return None

    stderr_text = (proc.stderr or "").strip()
    # If JSON is not supported, Vulture will complain about unrecognized arg
    if "unrecognized arguments: --json" in stderr_text:
        # Signal caller to try text mode
        return None

    raw = (proc.stdout or "").strip()
    if not raw:
        # No output => assume no dead code
        return _aggregate_items([])

    data = None

    # First attempt: raw as-is
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Second attempt: try to extract a JSON array substring
        array_sub = _extract_json_array(raw)
        if array_sub:
            try:
                data = json.loads(array_sub)
            except json.JSONDecodeError:
                data = None

    if data is None:
        # Could not parse JSON. Print a small hint and let caller decide.
        print("[VULTURE] Failed to parse JSON output (JSON mode). Output was:")
        print(raw[:500] + ("..." if len(raw) > 500 else ""))
        return None

    if isinstance(data, dict):
        if "results" in data and isinstance(data["results"], list):
            items_raw = data["results"]
        else:
            return _aggregate_items([])
    elif isinstance(data, list):
        items_raw = data
    else:
        return _aggregate_items([])

    items: List[Dict[str, Any]] = []
    for it in items_raw:
        if not isinstance(it, dict):
            continue
        # Keep the fields we care about
        items.append(
            {
                "type": it.get("type", "other"),
                "name": it.get("name", ""),
                "filename": it.get("filename", ""),
                "lineno": it.get("lineno"),
                "confidence": it.get("confidence"),
            }
        )

    return _aggregate_items(items)


# ---------------------------------------------------------------------------
# Text-mode helpers (for older Vulture versions)
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(r"^(?P<filename>.*?):(?P<lineno>\d+):\s*(?P<desc>.+)$")
_CONF_RE = re.compile(r"\((?P<conf>\d+)%\)")

def _infer_type_from_desc(desc: str) -> str:
    """
    Infer a deadcode 'type' from Vulture textual description.
    Examples of desc:
      - "unused function 'foo' (60%)"
      - "unused class 'Bar' (90%)"
      - "unreachable code"
    """
    lower = desc.lower()
    if "function" in lower:
        return "function"
    if "class" in lower:
        return "class"
    if "attribute" in lower:
        return "attribute"
    if "variable" in lower:
        return "variable"
    if "property" in lower:
        return "property"
    return "other"


def _extract_name_from_desc(desc: str) -> str:
    """
    Try to extract a name from the description, e.g. between quotes.
    """
    m = re.search(r"'([^']+)'", desc)
    if m:
        return m.group(1)
    return ""


def _run_vulture_text_mode(project_path: str, vulture_binary: str) -> Optional[Dict[str, Any]]:
    """
    Run Vulture in normal (text) mode and parse its output.

    Expected lines like:
      path/to/file.py:10: unused function 'foo' (60%)

    Returns metrics dict or None if something goes very wrong.
    """
    cmd = [vulture_binary, project_path]

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,  # non-zero exit is normal when dead code found
        )
    except FileNotFoundError:
        print(f"[VULTURE] Command not found: {vulture_binary}. Skipping Vulture analysis.")
        return None
    except Exception as e:
        print(f"[VULTURE] Error while running Vulture (text mode): {e}")
        return None

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    # If absolutely nothing was printed, assume no dead code.
    if not out and not err:
        return _aggregate_items([])

    # Vulture usually prints findings on stdout. If empty, we can also inspect stderr.
    text = out if out else err
    if not text:
        return _aggregate_items([])

    items: List[Dict[str, Any]] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = _LINE_RE.match(line)
        if not m:
            # Could be banner or something else; ignore
            continue

        filename = m.group("filename").strip()
        lineno_str = m.group("lineno")
        desc = m.group("desc").strip()

        try:
            lineno = int(lineno_str)
        except ValueError:
            lineno = None

        itype = _infer_type_from_desc(desc)
        name = _extract_name_from_desc(desc)

        conf = None
        m_conf = _CONF_RE.search(desc)
        if m_conf:
            try:
                conf = int(m_conf.group("conf"))
            except ValueError:
                conf = None

        items.append(
            {
                "type": itype,
                "name": name,
                "filename": filename,
                "lineno": lineno,
                "confidence": conf,
            }
        )

    return _aggregate_items(items)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_vulture_and_collect_deadcode(
    project_path: str,
    vulture_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Vulture on the given project_path and aggregate dead-code information.

    Strategy:
      1. Try JSON mode (vulture <path> --json).
      2. If JSON not supported or parsing fails, fall back to text mode.
      3. If everything fails, return {} (no metrics).
    """
    if not vulture_binary:
        # Vulture explicitly disabled
        return {}

    # 1) Try JSON mode
    metrics = _run_vulture_json_mode(project_path, vulture_binary)
    if metrics is not None:
        return metrics

    # 2) Fallback: text mode
    metrics = _run_vulture_text_mode(project_path, vulture_binary)
    if metrics is not None:
        return metrics

    # 3) Final fallback: no data
    return {}