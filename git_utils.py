# git_utils.py

import os
import fnmatch
from typing import List, Optional

from git import Repo, GitCommandError, TagReference


def detect_default_branch(repo: Repo) -> str:
    """
    Try to detect the default branch of the repository.
    Priority:
      1. 'master'
      2. 'main'
      3. repo.head.ref.name
    Fallback: 'master'
    """
    branches = [b.name for b in repo.branches]
    if "master" in branches:
        return "master"
    if "main" in branches:
        return "main"
    try:
        return repo.head.ref.name
    except TypeError:
        return "master"


def clone_or_update_repo(project_name: str, repos_dir: str) -> Optional[str]:
    """
    Clone or update a GitHub repo under repos_dir.
    Returns the local repo path or None on failure.
    """
    os.makedirs(repos_dir, exist_ok=True)
    repo_dir_name = project_name.replace("/", "__")
    repo_path = os.path.join(repos_dir, repo_dir_name)

    if not os.path.exists(repo_path):
        repo_url = f"https://github.com/{project_name}.git"
        print(f"[CLONE] {project_name} from {repo_url} -> {repo_path}")
        try:
            Repo.clone_from(repo_url, repo_path)
        except GitCommandError as e:
            print(f"  [ERROR] Cannot clone {project_name}: {e}")
            return None
    else:
        print(f"[UPDATE] {project_name} in {repo_path}")
        try:
            repo = Repo(repo_path)
            branch_name = detect_default_branch(repo)
            repo.git.checkout(branch_name)
            repo.remotes.origin.pull()
        except Exception as e:
            print(f"  [WARN] Cannot pull {project_name}: {e}")

    return repo_path


def list_release_tags(repo: Repo, pattern: Optional[str] = None) -> List[TagReference]:
    """
    Return the list of tags (treated as releases), sorted by commit date.
    If 'pattern' is provided (e.g., 'v*'), only tags whose names match the
    pattern are returned.
    """
    tags: List[TagReference] = list(repo.tags)

    if pattern:
        tags = [t for t in tags if fnmatch.fnmatch(t.name, pattern)]

    # sort tags by the commit date
    tags.sort(key=lambda t: t.commit.committed_datetime)
    return tags


def resolve_ref(repo: Repo, ref: str):
    """
    Resolve a tag/branch/SHA into a commit object.
    """
    return repo.commit(ref)