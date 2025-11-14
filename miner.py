# miner.py

import os
import re
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional, Dict, Set, Tuple, List, Any

import pandas as pd
from git import Repo, GitCommandError

from config import MiningConfig
from github_api import get_github_repo_stats
from dpy_runner import run_dpy_and_collect_smells
from git_utils import (
    detect_default_branch,
    clone_or_update_repo,
    list_release_tags,
    resolve_ref,
)
from bandit_runner import run_bandit_and_collect_vulns
from deadcode_runner import run_vulture_and_collect_deadcode


# =============================================================================
# Basic helpers
# =============================================================================


def _compute_repo_summary_on_branch(repo: Repo, branch_name: str) -> Tuple[int, int]:
    """
    Compute branch-level summary information:
      - total number of commits on the branch
      - number of distinct contributors (author name + email)
    """
    commits = list(repo.iter_commits(branch_name))
    repo_commit_count = len(commits)

    contributors_set = set()
    for c in commits:
        author_name = (c.author.name or "").strip()
        author_email = (c.author.email or "").strip()
        contributors_set.add((author_name, author_email))
    repo_contributors = len(contributors_set)

    return repo_commit_count, repo_contributors


def _fill_smell_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure smell-related columns are integer and NaN-safe.
    """
    if df.empty:
        return df

    smell_cols = [
        c
        for c in df.columns
        if c.startswith("impl_smell_")
        or c.startswith("design_smell_")
        or c in ("impl_smells_total", "design_smells_total")
    ]
    if smell_cols:
        df[smell_cols] = df[smell_cols].fillna(0).astype(int)

    return df


def _compute_repo_loc_on_disk(root_path: str) -> int:
    """
    Compute the number of lines of code in the repository, based on the current
    working tree on disk.

    This is a generic LOC count:
      - walks the filesystem under root_path
      - skips the .git directory
      - counts lines in all files (binary-safe, opened as bytes)
    """
    total = 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip the .git directory to avoid counting Git internals
        if ".git" in dirnames:
            dirnames.remove(".git")

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "rb") as f:
                    for _ in f:
                        total += 1
            except Exception:
                # Ignore files we cannot read
                continue
    return total


# =============================================================================
# Fixing commit detection (heuristic)
# =============================================================================

_FIX_KEYWORDS: List[str] = [
    "fix",
    "fixes",
    "fixed",
    "bug",
    "bugfix",
    "bug fix",
    "bugfixes",
    "hotfix",
    "patch",
    "repair",
    "repaired",
    "resolve",
    "resolves",
    "resolved",
]

_TRIVIAL_PATTERNS: List[str] = [
    "fix typo",
    "fix typos",
    "fix minor typo",
    "typo fix",
    "typos fix",
    "fix whitespace",
    "fix spacing",
    "fix indentation",
    "fix indent",
    "fix style",
    "fix styling",
    "fix formatting",
    "fix format",
    "fix lint",
    "lint fix",
    "fix doc",
    "fix docs",
    "fix documentation",
    "docs fix",
    "documentation fix",
    "fix comment",
    "fix comments",
    "fix note",
    "fix notes",
    "minor fix",
    "small fix",
    "tiny fix",
    "cosmetic fix",
]


def _detect_fixing_commit(message: str) -> Tuple[bool, List[str]]:
    """
    Heuristically detect whether a commit message indicates a fixing commit.

    Behaviour:
      - case-insensitive
      - ignores trivial fixes (typos, docs, formatting, whitespace)
      - ignores merge commits
    """
    if not message:
        return False, []

    original_message = message
    lower = message.lower()
    tags: List[str] = []

    # 1. Ignore merge commits (including merge pull requests)
    if lower.startswith("merge "):
        return False, []
    if "merge pull request" in lower:
        return False, []

    # 2. Ignore trivial fixes (typos/docs/formatting)
    for trivial in _TRIVIAL_PATTERNS:
        if trivial in lower:
            return False, []

    # 3. Real fixing keywords
    for kw in _FIX_KEYWORDS:
        if " " in kw:
            # multi-word keyword
            if kw in lower:
                tags.append("kw:" + kw)
        else:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, lower):
                tags.append("kw:" + kw)

    # 4. Issue references (#123...)
    issue_refs = re.findall(r"#\d+", original_message)
    for ref in issue_refs:
        tags.append("issue:" + ref)

    if not tags:
        return False, []

    tags = sorted(set(tags))
    return True, tags


# =============================================================================
# Bandit integration
# =============================================================================


def _add_bandit_metrics(
    metrics: Dict[str, Any],
    project_path: str,
    bandit_binary: Optional[str],
) -> Dict[str, Any]:
    """
    Run Bandit (if enabled) and merge vulnerability metrics into 'metrics' dict.
    """
    if not bandit_binary:
        return metrics

    bandit_metrics = run_bandit_and_collect_vulns(
        project_path=project_path,
        bandit_binary=bandit_binary,
    )
    if bandit_metrics:
        metrics.update(bandit_metrics)
    return metrics


# =============================================================================
# Vulture integration (dead code)
# =============================================================================


def _add_vulture_metrics(
    metrics: Dict[str, Any],
    project_path: str,
    vulture_binary: Optional[str],
) -> Dict[str, Any]:
    """
    Run Vulture (if enabled) and merge dead-code metrics into 'metrics' dict.

    This will add keys such as:
      - deadcode_items_total
      - deadcode_items_function
      - deadcode_items_class
      - deadcode_items_attribute
      - deadcode_items_variable
      - deadcode_items_property
      - deadcode_items_other
      - deadcode_items_summaries
    """
    if not vulture_binary:
        return metrics

    vulture_metrics = run_vulture_and_collect_deadcode(
        project_path=project_path,
        vulture_binary=vulture_binary,
    )
    if vulture_metrics:
        metrics.update(vulture_metrics)
    return metrics


# =============================================================================
# SZZ-like introducing commits (robust version)
# =============================================================================

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


def _szz_find_introducing_commits(repo: Repo, fix_commit) -> Set[str]:
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


# =============================================================================
# Commit-by-commit mining
# =============================================================================


def mine_repo_commits(
    config: MiningConfig,
    repo: Repo,
    project_name: str,
    repo_path: str,
    repo_stars: int,
    repo_forks: int,
    already_processed_shas: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """
    Mine one repository commit-by-commit with DPy.

    Features:
      - Real LOC: baseline at first commit + incremental deltas.
      - Fixing commit detection (heuristic).
      - SZZ-like algorithm: for fixing commits, find introducing commits.
      - Bandit vulnerability metrics.
      - Vulture dead-code metrics.
    """
    assert not repo.bare

    default_branch = detect_default_branch(repo)
    print("[BRANCH] {} -> {}".format(project_name, default_branch))

    commits = list(repo.iter_commits(default_branch, reverse=True))
    if config.max_commits and config.max_commits > 0:
        commits = commits[: config.max_commits]

    if not commits:
        print("  [INFO] No commits found on branch {} for {}".format(default_branch, project_name))
        return pd.DataFrame()

    repo_commit_count, repo_contributors = _compute_repo_summary_on_branch(
        repo, default_branch
    )

    if already_processed_shas is None:
        already_processed_shas = set()
    else:
        already_processed_shas = set(already_processed_shas)

    num_already_on_branch = sum(1 for c in commits if c.hexsha in already_processed_shas)
    if num_already_on_branch > 0:
        print(
            "  [CHECKPOINT] {}: {} commits already in CSV, will be skipped.".format(
                project_name, num_already_on_branch
            )
        )

    rows: List[Dict[str, Any]] = []
    original_head = repo.head.commit

    # Baseline LOC at the first commit of the branch
    first_commit = commits[0]
    base_loc = 0
    try:
        repo.git.checkout(first_commit.hexsha)
        base_loc = _compute_repo_loc_on_disk(repo.working_tree_dir)
        print("  [LOC] Baseline LOC at first commit {}: {}".format(first_commit.hexsha[:7], base_loc))
    except GitCommandError as e:
        print(
            "  [WARN] Could not checkout first commit {} to compute baseline LOC: {}".format(
                first_commit.hexsha[:7], e
            )
        )
        base_loc = 0

    current_loc_delta = 0

    try:
        for idx, commit in enumerate(commits, start=1):
            sha = commit.hexsha

            stats = commit.stats
            total_insertions = stats.total.get("insertions", 0)
            total_deletions = stats.total.get("deletions", 0)
            total_files_changed = stats.total.get("files", 0)
            total_churn = total_insertions + total_deletions

            if idx == 1:
                repo_loc = base_loc
            else:
                current_loc_delta += (total_insertions - total_deletions)
                repo_loc = base_loc + current_loc_delta

            commit_date = datetime.fromtimestamp(commit.committed_date)
            author_name = commit.author.name or "Unknown"
            message = (commit.message or "").strip()

            is_fix, fix_tags = _detect_fixing_commit(message)
            fix_tags_str = ";".join(fix_tags) if fix_tags else ""

            if sha in already_processed_shas:
                print(
                    "  [{}] ({}/{}) SKIP commit {} (already processed, repo_loc={})".format(
                        project_name, idx, len(commits), sha[:7], repo_loc
                    )
                )
                continue

            print(
                "  [{}] ({}/{}) commit {} (new, LOC={}, fix={})".format(
                    project_name, idx, len(commits), sha[:7], repo_loc, is_fix
                )
            )

            try:
                repo.git.checkout(sha)
            except GitCommandError as e:
                print("    [WARN] checkout failed for {}: {}".format(sha[:7], e))
                continue

            smell_metrics = run_dpy_and_collect_smells(
                project_path=repo.working_tree_dir,
                dpy_binary=config.dpy_binary,
            )

            metrics: Dict[str, Any] = {
                "project_name": project_name,
                "repo_path": repo_path,
                "branch": default_branch,
                "commit_sha": sha,
                "commit_date": commit_date,
                "author_name": author_name,
                "commit_message": message,
                "commit_insertions": total_insertions,
                "commit_deletions": total_deletions,
                "commit_files_changed": total_files_changed,
                "commit_churn": total_churn,
                "repo_stars": repo_stars,
                "repo_forks": repo_forks,
                "repo_loc": repo_loc,
                "repo_commit_count": repo_commit_count,
                "repo_contributors": repo_contributors,
                "ref_type": "commit",
                "ref_name": sha,
                "fix_commit": int(is_fix),
                "fix_commit_tags": fix_tags_str,
            }
            metrics.update(smell_metrics)

            metrics = _add_bandit_metrics(
                metrics=metrics,
                project_path=repo.working_tree_dir,
                bandit_binary=config.bandit_binary,
            )

            metrics = _add_vulture_metrics(
                metrics=metrics,
                project_path=repo.working_tree_dir,
                vulture_binary=config.vulture_binary,
            )

            if is_fix:
                introducing = _szz_find_introducing_commits(repo, commit)
                metrics["szz_introducing_commits"] = (
                    ",".join(sorted(introducing)) if introducing else ""
                )
                metrics["szz_introducing_commits_count"] = len(introducing)
            else:
                metrics["szz_introducing_commits"] = ""
                metrics["szz_introducing_commits_count"] = 0

            rows.append(metrics)

    finally:
        try:
            repo.git.checkout(original_head)
        except Exception:
            pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return _fill_smell_columns(df)


# =============================================================================
# Release-by-release (tags)
# =============================================================================


def mine_repo_releases(
    config: MiningConfig,
    repo: Repo,
    project_name: str,
    repo_path: str,
    repo_stars: int,
    repo_forks: int,
    already_processed_shas: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """
    Mine one repository tag-by-tag (release-by-release) with DPy.

    Repo LOC is computed for each tag by scanning the working tree on disk.

    We detect if the tag's commit is "fixing", but we do NOT run SZZ here.
    """
    assert not repo.bare

    default_branch = detect_default_branch(repo)
    print("[BRANCH] {} -> {} (for summary)".format(project_name, default_branch))

    repo_commit_count, repo_contributors = _compute_repo_summary_on_branch(
        repo, default_branch
    )

    tags = list_release_tags(repo, pattern=config.tag_pattern)
    if not tags:
        print(
            "  [INFO] No tags found for {} (pattern={!r})".format(
                project_name, config.tag_pattern
            )
        )
        return pd.DataFrame()

    if config.max_commits and config.max_commits > 0:
        tags = tags[: config.max_commits]

    if already_processed_shas is None:
        already_processed_shas = set()
    else:
        already_processed_shas = set(already_processed_shas)

    rows: List[Dict[str, Any]] = []
    original_head = repo.head.commit

    try:
        for idx, tag in enumerate(tags, start=1):
            commit = tag.commit
            sha = commit.hexsha

            if sha in already_processed_shas:
                print(
                    "  [{}] ({}/{}) SKIP tag {} ({}) already processed.".format(
                        project_name, idx, len(tags), tag.name, sha[:7]
                    )
                )
                continue

            stats = commit.stats
            total_insertions = stats.total.get("insertions", 0)
            total_deletions = stats.total.get("deletions", 0)
            total_files_changed = stats.total.get("files", 0)
            total_churn = total_insertions + total_deletions

            commit_date = datetime.fromtimestamp(commit.committed_date)
            author_name = commit.author.name or "Unknown"
            message = (commit.message or "").strip()

            is_fix, fix_tags = _detect_fixing_commit(message)
            fix_tags_str = ";".join(fix_tags) if fix_tags else ""

            print(
                "  [{}] ({}/{}) tag {} -> commit {} (new, fix={})".format(
                    project_name, idx, len(tags), tag.name, sha[:7], is_fix
                )
            )

            try:
                repo.git.checkout(sha)
            except GitCommandError as e:
                print("    [WARN] checkout failed for {}: {}".format(sha[:7], e))
                continue

            repo_loc = _compute_repo_loc_on_disk(repo.working_tree_dir)
            print(
                "    [LOC] tag {}, commit {} -> LOC={}".format(
                    tag.name, sha[:7], repo_loc
                )
            )

            smell_metrics = run_dpy_and_collect_smells(
                project_path=repo.working_tree_dir,
                dpy_binary=config.dpy_binary,
            )

            metrics: Dict[str, Any] = {
                "project_name": project_name,
                "repo_path": repo_path,
                "branch": default_branch,
                "commit_sha": sha,
                "commit_date": commit_date,
                "author_name": author_name,
                "commit_message": message,
                "commit_insertions": total_insertions,
                "commit_deletions": total_deletions,
                "commit_files_changed": total_files_changed,
                "commit_churn": total_churn,
                "repo_stars": repo_stars,
                "repo_forks": repo_forks,
                "repo_loc": repo_loc,
                "repo_commit_count": repo_commit_count,
                "repo_contributors": repo_contributors,
                "ref_type": "tag",
                "ref_name": tag.name,
                "fix_commit": int(is_fix),
                "fix_commit_tags": fix_tags_str,
                "szz_introducing_commits": "",
                "szz_introducing_commits_count": 0,
            }
            metrics.update(smell_metrics)

            metrics = _add_bandit_metrics(
                metrics=metrics,
                project_path=repo.working_tree_dir,
                bandit_binary=config.bandit_binary,
            )

            metrics = _add_vulture_metrics(
                metrics=metrics,
                project_path=repo.working_tree_dir,
                vulture_binary=config.vulture_binary,
            )

            rows.append(metrics)

    finally:
        try:
            repo.git.checkout(original_head)
        except Exception:
            pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return _fill_smell_columns(df)


# =============================================================================
# Single-version (single ref)
# =============================================================================


def mine_repo_single_version(
    config: MiningConfig,
    repo: Repo,
    project_name: str,
    repo_path: str,
    repo_stars: int,
    repo_forks: int,
    already_processed_shas: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """
    Mine one repository at a single ref (tag/branch/SHA) with DPy.

    Repo LOC is computed from the working tree after checkout.

    Note: we detect if that ref is "fixing", but we do NOT run SZZ here.
    """
    assert not repo.bare

    if not config.single_ref:
        raise ValueError(
            "single_ref must be set when analysis_mode='version'. "
            "Use MiningConfig.single_ref, --ref in the CLI, or the GUI field."
        )

    default_branch = detect_default_branch(repo)
    print("[BRANCH] {} -> {} (for summary)".format(project_name, default_branch))

    repo_commit_count, repo_contributors = _compute_repo_summary_on_branch(
        repo, default_branch
    )

    if already_processed_shas is None:
        already_processed_shas = set()
    else:
        already_processed_shas = set(already_processed_shas)

    commit = resolve_ref(repo, config.single_ref)
    sha = commit.hexsha

    if sha in already_processed_shas:
        print(
            "  [{}] Single ref {} ({}) already processed. Skipping.".format(
                project_name, config.single_ref, sha[:7]
            )
        )
        return pd.DataFrame()

    stats = commit.stats
    total_insertions = stats.total.get("insertions", 0)
    total_deletions = stats.total.get("deletions", 0)
    total_files_changed = stats.total.get("files", 0)
    total_churn = total_insertions + total_deletions

    commit_date = datetime.fromtimestamp(commit.committed_date)
    author_name = commit.author.name or "Unknown"
    message = (commit.message or "").strip()

    is_fix, fix_tags = _detect_fixing_commit(message)
    fix_tags_str = ";".join(fix_tags) if fix_tags else ""

    rows: List[Dict[str, Any]] = []
    original_head = repo.head.commit

    try:
        print(
            "  [{}] single ref {} -> commit {} (new, fix={})".format(
                project_name, config.single_ref, sha[:7], is_fix
            )
        )

        try:
            repo.git.checkout(sha)
        except GitCommandError as e:
            print("    [WARN] checkout failed for {}: {}".format(sha[:7], e))
            return pd.DataFrame()

        repo_loc = _compute_repo_loc_on_disk(repo.working_tree_dir)
        print(
            "    [LOC] single ref {}, commit {} -> LOC={}".format(
                config.single_ref, sha[:7], repo_loc
            )
        )

        smell_metrics = run_dpy_and_collect_smells(
            project_path=repo.working_tree_dir,
            dpy_binary=config.dpy_binary,
        )

        metrics: Dict[str, Any] = {
            "project_name": project_name,
            "repo_path": repo_path,
            "branch": default_branch,
            "commit_sha": sha,
            "commit_date": commit_date,
            "author_name": author_name,
            "commit_message": message,
            "commit_insertions": total_insertions,
            "commit_deletions": total_deletions,
            "commit_files_changed": total_files_changed,
            "commit_churn": total_churn,
            "repo_stars": repo_stars,
            "repo_forks": repo_forks,
            "repo_loc": repo_loc,
            "repo_commit_count": repo_commit_count,
            "repo_contributors": repo_contributors,
            "ref_type": "version",
            "ref_name": config.single_ref,
            "fix_commit": int(is_fix),
            "fix_commit_tags": fix_tags_str,
            "szz_introducing_commits": "",
            "szz_introducing_commits_count": 0,
        }
        metrics.update(smell_metrics)

        metrics = _add_bandit_metrics(
            metrics=metrics,
            project_path=repo.working_tree_dir,
            bandit_binary=config.bandit_binary,
        )

        metrics = _add_vulture_metrics(
            metrics=metrics,
            project_path=repo.working_tree_dir,
            vulture_binary=config.vulture_binary,
        )

        rows.append(metrics)

    finally:
        try:
            repo.git.checkout(original_head)
        except Exception:
            pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return _fill_smell_columns(df)


# =============================================================================
# Backwards-compatible wrapper
# =============================================================================


def mine_repo_with_dpy(
    repo_path: str,
    project_name: str,
    dpy_binary: str = "./DPy",
    max_commits: int = 0,
    already_processed_shas: Optional[Set[str]] = None,
    repo_stars: int = 0,
    repo_forks: int = 0,
) -> pd.DataFrame:
    """
    Backwards-compatible wrapper that preserves the old API, but internally
    uses commit-by-commit mining in 'commits' mode.
    Bandit and Vulture are not run in this legacy path.
    """
    repo = Repo(repo_path)
    cfg = MiningConfig(
        input_csv="",
        output_csv="",
        repos_dir=os.path.dirname(repo_path),
        dpy_binary=dpy_binary,
        max_commits=max_commits,
        github_token=None,
        jobs=1,
        analysis_mode="commits",
        bandit_binary=None,
        vulture_binary=None,
    )
    return mine_repo_commits(
        config=cfg,
        repo=repo,
        project_name=project_name,
        repo_path=repo_path,
        repo_stars=repo_stars,
        repo_forks=repo_forks,
        already_processed_shas=already_processed_shas or set(),
    )


# =============================================================================
# Per-project worker and high-level orchestration
# =============================================================================


def process_one_project(
    project_name: str,
    config: MiningConfig,
    already_processed_shas,
) -> Optional[Tuple[str, pd.DataFrame]]:
    """
    Worker function executed in a separate process.
    Dispatches to the appropriate mining mode.
    """
    print("\n=== PROJECT (worker): {} ===".format(project_name))

    repo_path = clone_or_update_repo(project_name, config.repos_dir)
    if repo_path is None or not os.path.exists(repo_path):
        print("  [SKIP] Skipping {} (repo not available)".format(project_name))
        return None

    repo_stars, repo_forks = get_github_repo_stats(
        project_name=project_name,
        github_token=config.github_token,
    )
    print("  [GITHUB] {}: stars={}, forks={}".format(project_name, repo_stars, repo_forks))

    repo = Repo(repo_path)

    mode = (config.analysis_mode or "commits").lower()
    if mode not in {"commits", "releases", "version"}:
        print(
            "  [ERROR] Unknown analysis mode '{}', falling back to 'commits'.".format(
                config.analysis_mode
            )
        )
        mode = "commits"

    if mode == "commits":
        df_repo = mine_repo_commits(
            config=config,
            repo=repo,
            project_name=project_name,
            repo_path=repo_path,
            repo_stars=repo_stars,
            repo_forks=repo_forks,
            already_processed_shas=already_processed_shas,
        )
    elif mode == "releases":
        df_repo = mine_repo_releases(
            config=config,
            repo=repo,
            project_name=project_name,
            repo_path=repo_path,
            repo_stars=repo_stars,
            repo_forks=repo_forks,
            already_processed_shas=already_processed_shas,
        )
    else:  # "version"
        df_repo = mine_repo_single_version(
            config=config,
            repo=repo,
            project_name=project_name,
            repo_path=repo_path,
            repo_stars=repo_stars,
            repo_forks=repo_forks,
            already_processed_shas=already_processed_shas,
        )

    if df_repo.empty:
        print("  [INFO] No new rows to save for {}".format(project_name))
        return None

    return project_name, df_repo


def run_mining(config: MiningConfig) -> None:
    """
    High-level entry point used by CLI and GUI.
    Uses checkpointing and is resilient to CTRL+C (KeyboardInterrupt).
    """
    processed_by_project: Dict[str, Set[str]] = {}
    output_exists = os.path.exists(config.output_csv)

    if output_exists:
        print("[CHECKPOINT] Loading existing output from {}".format(config.output_csv))
        try:
            df_existing = pd.read_csv(
                config.output_csv, usecols=["project_name", "commit_sha"]
            )
            for proj, grp in df_existing.groupby("project_name"):
                processed_by_project[proj] = set(grp["commit_sha"].astype(str))
            print(
                "[CHECKPOINT] Projects already in CSV: {}".format(
                    len(processed_by_project)
                )
            )
        except Exception as e:
            print(
                "[CHECKPOINT] Problem reading {} as checkpoint: {}".format(
                    config.output_csv, e
                )
            )
            print("             Proceeding as if no checkpoint exists.")
            processed_by_project = {}
            output_exists = False

    print("[INPUT] Reading {}".format(config.input_csv))
    df_input = pd.read_csv(config.input_csv)

    if "ProjectName" not in df_input.columns:
        raise ValueError("Input CSV must contain a 'ProjectName' column.")

    project_names = (
        df_input["ProjectName"].dropna().astype(str).str.strip().unique()
    )

    print("[INFO] Projects found: {}".format(len(project_names)))

    if not project_names.size:
        print("[DONE] No projects to process.")
        return

    print("[PARALLEL] Starting up to {} parallel processes.".format(config.jobs))

    executor = ProcessPoolExecutor(max_workers=config.jobs)
    try:
        future_to_project: Dict[Any, str] = {}
        for project_name in project_names:
            already_processed_shas = processed_by_project.get(project_name, set())
            future = executor.submit(
                process_one_project,
                project_name,
                config,
                already_processed_shas,
            )
            future_to_project[future] = project_name

        try:
            for future in as_completed(future_to_project):
                project_name = future_to_project[future]
                try:
                    result = future.result()
                except Exception as e:
                    print("[ERROR] Worker for {} raised an exception: {}".format(project_name, e))
                    continue

                if result is None:
                    continue

                proj_name_res, df_repo = result

                mode = "a" if output_exists else "w"
                header = not output_exists
                df_repo.to_csv(config.output_csv, mode=mode, header=header, index=False)
                output_exists = True

                new_shas = set(df_repo["commit_sha"].astype(str))
                if proj_name_res in processed_by_project:
                    processed_by_project[proj_name_res].update(new_shas)
                else:
                    processed_by_project[proj_name_res] = new_shas

                print(
                    "  [OUTPUT] Added {} rows for {} to {}".format(
                        len(df_repo), proj_name_res, config.output_csv
                    )
                )

        except KeyboardInterrupt:
            print("\n[SAFE EXIT] KeyboardInterrupt received (CTRL+C).")
            print("            Waiting for running workers to finish current repositories...")
        finally:
            executor.shutdown(wait=True, cancel_futures=False)

    finally:
        if not output_exists:
            print("[DONE] No data to save (no repo processed successfully).")
        else:
            print("\n[DONE] Results written/updated in: {}".format(config.output_csv))