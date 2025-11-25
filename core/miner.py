import os
import re
from datetime import datetime
from typing import List, Dict, Any, Set, Optional
import pandas as pd
from git import Repo, GitCommandError

from config import MiningConfig
from models.metrics import CommitMetrics
from core.szz import szz_find_introducing_commits
from analyzers.bandit_analyzer import BanditAnalyzer
from analyzers.vulture_analyzer import VultureAnalyzer
from analyzers.dpy_analyzer import DPyAnalyzer
from utils.git_utils import detect_default_branch, list_release_tags, resolve_ref
from utils.github_api import get_issue_body, get_issue_comments

# Move these constants here or to a utils file
_FIX_KEYWORDS = [
    "fix", "fixes", "fixed", "bug", "bugfix", "bug fix", "bugfixes",
    "hotfix", "patch", "repair", "repaired", "resolve", "resolves", "resolved",
]

_TRIVIAL_PATTERNS = [
    "fix typo", "fix typos", "fix minor typo", "typo fix", "typos fix",
    "fix whitespace", "fix spacing", "fix indentation", "fix indent",
    "fix style", "fix styling", "fix formatting", "fix format",
    "fix lint", "lint fix", "fix doc", "fix docs", "fix documentation",
    "docs fix", "documentation fix", "fix comment", "fix comments",
    "fix note", "fix notes", "minor fix", "small fix", "tiny fix",
    "cosmetic fix",
]

def _detect_fixing_commit(message: str) -> tuple[bool, List[str]]:
    if not message:
        return False, []

    original_message = message
    lower = message.lower()
    tags: List[str] = []

    if lower.startswith("merge "):
        return False, []
    if "merge pull request" in lower:
        return False, []

    for trivial in _TRIVIAL_PATTERNS:
        if trivial in lower:
            return False, []

    for kw in _FIX_KEYWORDS:
        if " " in kw:
            if kw in lower:
                tags.append("kw:" + kw)
        else:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, lower):
                tags.append("kw:" + kw)

    issue_refs = re.findall(r"#\d+", original_message)
    for ref in issue_refs:
        tags.append("issue:" + ref)

    if not tags:
        return False, []

    tags = sorted(set(tags))
    return True, tags

def _compute_repo_loc_on_disk(root_path: str) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        if ".git" in dirnames:
            dirnames.remove(".git")

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "rb") as f:
                    for _ in f:
                        total += 1
            except Exception:
                continue
    return total

def _compute_repo_summary_on_branch(repo: Repo, branch_name: str) -> tuple[int, int]:
    commits = list(repo.iter_commits(branch_name))
    repo_commit_count = len(commits)
    contributors_set = set()
    for c in commits:
        author_name = (c.author.name or "").strip()
        author_email = (c.author.email or "").strip()
        contributors_set.add((author_name, author_email))
    repo_contributors = len(contributors_set)
    return repo_commit_count, repo_contributors


class RepositoryMiner:
    def __init__(self, config: MiningConfig):
        self.config = config
        self.bandit_analyzer = BanditAnalyzer()
        self.vulture_analyzer = VultureAnalyzer()
        self.dpy_analyzer = DPyAnalyzer()

    def mine(self, repo: Repo, project_name: str, repo_path: str, repo_stars: int, repo_forks: int, already_processed_shas: Set[str]) -> pd.DataFrame:
        if self.config.analysis_mode == "commits":
            return self._mine_commits(repo, project_name, repo_path, repo_stars, repo_forks, already_processed_shas)
        elif self.config.analysis_mode == "releases":
            return self._mine_releases(repo, project_name, repo_path, repo_stars, repo_forks, already_processed_shas)
        elif self.config.analysis_mode == "version":
            return self._mine_single_version(repo, project_name, repo_path, repo_stars, repo_forks, already_processed_shas)
        else:
            raise ValueError(f"Unknown analysis mode: {self.config.analysis_mode}")

    def _mine_commits(self, repo: Repo, project_name: str, repo_path: str, repo_stars: int, repo_forks: int, already_processed_shas: Set[str]) -> pd.DataFrame:
        default_branch = detect_default_branch(repo)
        print(f"[BRANCH] {project_name} -> {default_branch}")

        commits = list(repo.iter_commits(default_branch, reverse=True))
        if self.config.max_commits and self.config.max_commits > 0:
            commits = commits[: self.config.max_commits]

        if not commits:
            return pd.DataFrame()

        repo_commit_count, repo_contributors = _compute_repo_summary_on_branch(repo, default_branch)

        rows = []
        original_head = repo.head.commit

        first_commit = commits[0]
        base_loc = 0
        try:
            repo.git.checkout(first_commit.hexsha)
            base_loc = _compute_repo_loc_on_disk(repo.working_tree_dir)
        except GitCommandError:
            base_loc = 0

        current_loc_delta = 0

        try:
            for idx, commit in enumerate(commits, start=1):
                sha = commit.hexsha
                if sha in already_processed_shas:
                    continue

                stats = commit.stats
                total_insertions = stats.total.get("insertions", 0)
                total_deletions = stats.total.get("deletions", 0)
                total_files_changed = stats.total.get("files", 0)
                total_churn = total_insertions + total_deletions
                
                # Extract list of modified files
                modified_files = list(stats.files.keys()) if stats.files else []
                modified_files_str = ",".join(modified_files)

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

                print(f"  [{project_name}] ({idx}/{len(commits)}) commit {sha[:7]} (new, LOC={repo_loc}, fix={is_fix})")

                try:
                    repo.git.checkout(sha)
                except GitCommandError:
                    continue

                metrics = CommitMetrics(
                    project_name=project_name,
                    repo_path=repo_path,
                    branch=default_branch,
                    commit_sha=sha,
                    commit_date=commit_date,
                    author_name=author_name,
                    commit_message=message,
                    commit_insertions=total_insertions,
                    commit_deletions=total_deletions,
                    commit_files_changed=total_files_changed,
                    commit_churn=total_churn,
                    commit_files=modified_files_str,
                    repo_stars=repo_stars,
                    repo_forks=repo_forks,
                    repo_loc=repo_loc,
                    repo_commit_count=repo_commit_count,
                    repo_contributors=repo_contributors,
                    ref_type="commit",
                    ref_name=sha,
                    is_release=False,  # Regular commits are not releases
                    fix_commit=int(is_fix),
                    fix_commit_tags=fix_tags_str,
                )

                # Analyzers
                metrics.extra_metrics.update(self.dpy_analyzer.run(repo.working_tree_dir, self.config.dpy_binary))
                metrics.extra_metrics.update(self.bandit_analyzer.run(repo.working_tree_dir, self.config.bandit_binary))
                metrics.extra_metrics.update(self.vulture_analyzer.run(repo.working_tree_dir, self.config.vulture_binary))

                if is_fix:
                    introducing = szz_find_introducing_commits(repo, commit)
                    metrics.szz_introducing_commits = ",".join(sorted(introducing)) if introducing else ""
                    metrics.szz_introducing_commits_count = len(introducing)
                    
                    # Fetch issue bodies and comments
                    import json
                    issue_bodies = []
                    all_comments = []
                    
                    for tag in fix_tags:
                        if tag.startswith("issue:"):
                            issue_num = tag.split(":", 1)[1].lstrip("#")
                            
                            # Get issue body
                            body = get_issue_body(project_name, issue_num, self.config.github_token)
                            if body:
                                issue_bodies.append(f"Issue #{issue_num}: {body}")
                            
                            # Get issue comments (developer conversations)
                            comments = get_issue_comments(project_name, issue_num, self.config.github_token)
                            if comments:
                                for comment in comments:
                                    all_comments.append({
                                        "issue": issue_num,
                                        "user": comment["user"],
                                        "created_at": comment["created_at"],
                                        "body": comment["body"]
                                    })
                    
                    metrics.issue_bodies = "\n---\n".join(issue_bodies)
                    metrics.issue_comments = json.dumps(all_comments, ensure_ascii=False) if all_comments else ""


                rows.append(metrics.to_dict())

        finally:
            try:
                repo.git.checkout(original_head)
            except Exception:
                pass

        return pd.DataFrame(rows)

    def _mine_releases(self, repo: Repo, project_name: str, repo_path: str, repo_stars: int, repo_forks: int, already_processed_shas: Set[str]) -> pd.DataFrame:
        # Implementation similar to mine_repo_releases but using CommitMetrics and Analyzers
        # For brevity, I'll implement a simplified version or copy logic if needed.
        # Assuming similar structure to _mine_commits but iterating tags.
        default_branch = detect_default_branch(repo)
        repo_commit_count, repo_contributors = _compute_repo_summary_on_branch(repo, default_branch)
        
        tags = list_release_tags(repo, pattern=self.config.tag_pattern)
        if self.config.max_commits and self.config.max_commits > 0:
            tags = tags[: self.config.max_commits]

        rows = []
        original_head = repo.head.commit

        try:
            for idx, tag in enumerate(tags, start=1):
                commit = tag.commit
                sha = commit.hexsha
                if sha in already_processed_shas:
                    continue
                
                # ... (similar logic for stats, checkout, analyzers)
                # Simplified for this step, but fully implementing:
                stats = commit.stats
                total_insertions = stats.total.get("insertions", 0)
                total_deletions = stats.total.get("deletions", 0)
                total_files_changed = stats.total.get("files", 0)
                total_churn = total_insertions + total_deletions
                
                # Extract list of modified files
                modified_files = list(stats.files.keys()) if stats.files else []
                modified_files_str = ",".join(modified_files)
                
                commit_date = datetime.fromtimestamp(commit.committed_date)
                author_name = commit.author.name or "Unknown"
                message = (commit.message or "").strip()
                is_fix, fix_tags = _detect_fixing_commit(message)
                fix_tags_str = ";".join(fix_tags) if fix_tags else ""

                print(f"  [{project_name}] ({idx}/{len(tags)}) tag {tag.name} -> commit {sha[:7]}")

                try:
                    repo.git.checkout(sha)
                except GitCommandError:
                    continue
                
                repo_loc = _compute_repo_loc_on_disk(repo.working_tree_dir)

                metrics = CommitMetrics(
                    project_name=project_name,
                    repo_path=repo_path,
                    branch=default_branch,
                    commit_sha=sha,
                    commit_date=commit_date,
                    author_name=author_name,
                    commit_message=message,
                    commit_insertions=total_insertions,
                    commit_deletions=total_deletions,
                    commit_files_changed=total_files_changed,
                    commit_churn=total_churn,
                    commit_files=modified_files_str,
                    repo_stars=repo_stars,
                    repo_forks=repo_forks,
                    repo_loc=repo_loc,
                    repo_commit_count=repo_commit_count,
                    repo_contributors=repo_contributors,
                    ref_type="tag",
                    ref_name=tag.name,
                    is_release=True,  # Tagged commits are releases
                    fix_commit=int(is_fix),
                    fix_commit_tags=fix_tags_str,
                )
                
                metrics.extra_metrics.update(self.dpy_analyzer.run(repo.working_tree_dir, self.config.dpy_binary))
                metrics.extra_metrics.update(self.bandit_analyzer.run(repo.working_tree_dir, self.config.bandit_binary))
                metrics.extra_metrics.update(self.vulture_analyzer.run(repo.working_tree_dir, self.config.vulture_binary))
                
                rows.append(metrics.to_dict())

        finally:
            try:
                repo.git.checkout(original_head)
            except Exception:
                pass
        
        return pd.DataFrame(rows)

    def _mine_single_version(self, repo: Repo, project_name: str, repo_path: str, repo_stars: int, repo_forks: int, already_processed_shas: Set[str]) -> pd.DataFrame:
        # Implementation for single version
        default_branch = detect_default_branch(repo)
        repo_commit_count, repo_contributors = _compute_repo_summary_on_branch(repo, default_branch)
        
        commit = resolve_ref(repo, self.config.single_ref)
        sha = commit.hexsha
        
        if sha in already_processed_shas:
            return pd.DataFrame()

        rows = []
        original_head = repo.head.commit
        
        try:
            print(f"  [{project_name}] single ref {self.config.single_ref} -> commit {sha[:7]}")
            repo.git.checkout(sha)
            repo_loc = _compute_repo_loc_on_disk(repo.working_tree_dir)
            
            stats = commit.stats
            total_insertions = stats.total.get("insertions", 0)
            total_deletions = stats.total.get("deletions", 0)
            total_files_changed = stats.total.get("files", 0)
            total_churn = total_insertions + total_deletions
            
            # Extract list of modified files
            modified_files = list(stats.files.keys()) if stats.files else []
            modified_files_str = ",".join(modified_files)
            
            commit_date = datetime.fromtimestamp(commit.committed_date)
            author_name = commit.author.name or "Unknown"
            message = (commit.message or "").strip()
            is_fix, fix_tags = _detect_fixing_commit(message)
            fix_tags_str = ";".join(fix_tags) if fix_tags else ""
            
            metrics = CommitMetrics(
                project_name=project_name,
                repo_path=repo_path,
                branch=default_branch,
                commit_sha=sha,
                commit_date=commit_date,
                author_name=author_name,
                commit_message=message,
                commit_insertions=total_insertions,
                commit_deletions=total_deletions,
                commit_files_changed=total_files_changed,
                commit_churn=total_churn,
                commit_files=modified_files_str,
                repo_stars=repo_stars,
                repo_forks=repo_forks,
                repo_loc=repo_loc,
                repo_commit_count=repo_commit_count,
                repo_contributors=repo_contributors,
                ref_type="ref",
                ref_name=self.config.single_ref,
                is_release=False,  # Single version analysis, not necessarily a release
                fix_commit=int(is_fix),
                fix_commit_tags=fix_tags_str,
            )
            
            metrics.extra_metrics.update(self.dpy_analyzer.run(repo.working_tree_dir, self.config.dpy_binary))
            metrics.extra_metrics.update(self.bandit_analyzer.run(repo.working_tree_dir, self.config.bandit_binary))
            metrics.extra_metrics.update(self.vulture_analyzer.run(repo.working_tree_dir, self.config.vulture_binary))
            
            rows.append(metrics.to_dict())
            
        finally:
            try:
                repo.git.checkout(original_head)
            except Exception:
                pass
                
        return pd.DataFrame(rows)
