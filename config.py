# config.py

from dataclasses import dataclass
from typing import Optional


@dataclass
class MiningConfig:
    """
    Global configuration for the mining process.
    """
    input_csv: str
    output_csv: str
    repos_dir: str
    dpy_binary: str

    max_commits: int = 0
    github_token: Optional[str] = None
    jobs: int = 1

    # Analysis mode:
    #   - "commits": commit-by-commit
    #   - "releases": tag-by-tag
    #   - "version": single ref (tag/branch/SHA)
    analysis_mode: str = "commits"
    tag_pattern: Optional[str] = None
    single_ref: Optional[str] = None

    # Optional external tools
    bandit_binary: Optional[str] = None      # e.g. "bandit"
    vulture_binary: Optional[str] = None     # e.g. "vulture"
    smell_ai_path: Optional[str] = None      # e.g. "./smell_ai"
    
    # Timeout per project (in minutes, 0 = no timeout)
    max_project_time_minutes: int = 0
    
    # OpenAI API key for developer classification
    openai_api_key: Optional[str] = None