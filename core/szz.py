import re
from typing import Set, Optional
from git import Repo, GitCommandError

_HUNK_RE = re.compile(
    r"@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)

def _blame_line_commit_sha(
    repo: Repo,
    parent_sha: str,
    path: str,
    line_no: int,
) -> Optional[str]:
    """
    Run git blame on a single line in a file at parent_sha and return the
    introducing commit SHA for that line. Returns None on failure.
    """
    try:
        out = repo.git.blame(
            parent_sha,
            "-L",
            f"{line_no},{line_no}",
            "--",
            path,
        )
    except GitCommandError:
        return None
    except Exception:
        return None

    out = out.strip()
    if not out:
        return None

    first_token = out.split()[0]
    sha = first_token.split("^")[0].split("~")[0]
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
        return sha
    return None


def szz_find_introducing_commits(repo: Repo, fix_commit) -> Set[str]:
    """
    SZZ-like algorithm: for a fixing commit, find introducing commits by:

      1. Taking the parent commit.
      2. Computing the diff with create_patch=True.
      3. For every deleted line ('-') in the patch, run git blame on the parent
         to see which commit introduced that line.

    Returns a set of introducing commit SHAs.
    """
    introducing_shas: Set[str] = set()

    if not fix_commit.parents:
        return introducing_shas
    parent = fix_commit.parents[0]

    try:
        diffs = parent.diff(fix_commit, create_patch=True)
    except GitCommandError:
        return introducing_shas
    except Exception:
        return introducing_shas

    for d in diffs:
        if d.new_file:
            continue

        path = d.a_path or d.b_path
        if not path:
            continue

        patch_bytes = d.diff
        if not patch_bytes:
            continue

        try:
            patch_text = patch_bytes.decode("utf-8", errors="ignore")
        except Exception:
            continue

        old_line_no: Optional[int] = None

        for line in patch_text.splitlines():
            if line.startswith("@@"):
                m = _HUNK_RE.match(line)
                if not m:
                    old_line_no = None
                    continue
                old_start = int(m.group("old_start"))
                old_line_no = old_start
                continue

            if old_line_no is None:
                continue

            if line.startswith("---") or line.startswith("+++"):
                continue

            if line.startswith("-"):
                blamed_sha = _blame_line_commit_sha(
                    repo=repo,
                    parent_sha=parent.hexsha,
                    path=path,
                    line_no=old_line_no,
                )
                if blamed_sha:
                    introducing_shas.add(blamed_sha)
                old_line_no += 1
            elif line.startswith("+"):
                continue
            else:
                old_line_no += 1

    return introducing_shas
