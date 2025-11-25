from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class CommitMetrics:
    project_name: str
    repo_path: str
    branch: str
    commit_sha: str
    commit_date: datetime
    author_name: str
    commit_message: str
    commit_insertions: int
    commit_deletions: int
    commit_files_changed: int
    commit_churn: int
    commit_files: str = ""  # Comma-separated list of modified files
    repo_stars: int
    repo_forks: int
    repo_loc: int
    repo_commit_count: int
    repo_contributors: int
    ref_type: str
    ref_name: str
    is_release: bool = False  # True if commit is tagged as a release
    fix_commit: int
    fix_commit_tags: str
    szz_introducing_commits: str = ""
    szz_introducing_commits_count: int = 0
    issue_bodies: str = ""
    issue_comments: str = ""  # JSON string of comments
    repo_all_issues: str = ""  # JSON string of all repository issues
    
    # Dynamic fields for smells and other tools
    extra_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "project_name": self.project_name,
            "repo_path": self.repo_path,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "commit_date": self.commit_date,
            "author_name": self.author_name,
            "commit_message": self.commit_message,
            "commit_insertions": self.commit_insertions,
            "commit_deletions": self.commit_deletions,
            "commit_files_changed": self.commit_files_changed,
            "commit_churn": self.commit_churn,
            "commit_files": self.commit_files,
            "repo_stars": self.repo_stars,
            "repo_forks": self.repo_forks,
            "repo_loc": self.repo_loc,
            "repo_commit_count": self.repo_commit_count,
            "repo_contributors": self.repo_contributors,
            "ref_type": self.ref_type,
            "ref_name": self.ref_name,
            "is_release": self.is_release,
            "fix_commit": self.fix_commit,
            "fix_commit_tags": self.fix_commit_tags,
            "szz_introducing_commits": self.szz_introducing_commits,
            "szz_introducing_commits_count": self.szz_introducing_commits_count,
            "issue_bodies": self.issue_bodies,
            "issue_comments": self.issue_comments,
            "repo_all_issues": self.repo_all_issues,
        }
        base.update(self.extra_metrics)
        return base
