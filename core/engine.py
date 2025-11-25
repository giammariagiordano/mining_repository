import os
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError
from typing import Dict, Set, Any
import json

from config import MiningConfig
from core.miner import RepositoryMiner
from utils.git_utils import clone_or_update_repo
from utils.github_api import get_github_repo_stats, get_all_issues

def process_one_project(project_name: str, config: MiningConfig, already_processed_shas: Set[str]) -> tuple[str, pd.DataFrame]:
    print(f"[START] Processing {project_name}...")
    
    try:
        repo_path = clone_or_update_repo(project_name, config.repos_dir)
        if not repo_path:
            print(f"[ERROR] Failed to clone/update {project_name}")
            return project_name, pd.DataFrame()
        
        from git import Repo
        repo = Repo(repo_path)
    except Exception as e:
        print(f"[ERROR] Failed to clone/update {project_name}: {e}")
        return project_name, pd.DataFrame()

    stars, forks = get_github_repo_stats(project_name, config.github_token)
    
    # Fetch all repository issues
    print(f"[ISSUES] Fetching all issues for {project_name}...")
    all_issues = get_all_issues(project_name, config.github_token)
    all_issues_json = json.dumps(all_issues, ensure_ascii=False) if all_issues else ""
    print(f"[ISSUES] Found {len(all_issues)} issues for {project_name}")
    
    miner = RepositoryMiner(config)
    try:
        df = miner.mine(repo, project_name, repo_path, stars, forks, already_processed_shas)
        
        # Add all_issues to every row
        if not df.empty:
            df["repo_all_issues"] = all_issues_json
        
        return project_name, df
    except Exception as e:
        print(f"[ERROR] Mining failed for {project_name}: {e}")
        return project_name, pd.DataFrame()



class MiningEngine:
    def __init__(self, config: MiningConfig, progress_callback=None):
        self.config = config
        self.progress_callback = progress_callback

    def run(self):
        processed_by_project: Dict[str, Set[str]] = {}
        output_exists = os.path.exists(self.config.output_csv)

        if output_exists:
            print(f"[CHECKPOINT] Loading existing output from {self.config.output_csv}")
            try:
                df_existing = pd.read_csv(self.config.output_csv, usecols=["project_name", "commit_sha"])
                for proj, grp in df_existing.groupby("project_name"):
                    processed_by_project[proj] = set(grp["commit_sha"].astype(str))
            except Exception as e:
                print(f"[CHECKPOINT] Problem reading checkpoint: {e}")
                processed_by_project = {}
                output_exists = False

        print(f"[INPUT] Reading {self.config.input_csv}")
        df_input = pd.read_csv(self.config.input_csv)
        if "ProjectName" not in df_input.columns:
            raise ValueError("Input CSV must contain a 'ProjectName' column.")

        project_names = df_input["ProjectName"].dropna().astype(str).str.strip().unique()

        if not project_names.size:
            print("[DONE] No projects to process.")
            return

        max_workers = self.config.jobs if self.config.jobs > 0 else None
        print(f"[PARALLEL] Starting parallel processes (max_workers={max_workers}).")

        executor = ProcessPoolExecutor(max_workers=max_workers)
        try:
            future_to_project = {}
            for project_name in project_names:
                already_processed = processed_by_project.get(project_name, set())
                future = executor.submit(process_one_project, project_name, self.config, already_processed)
                future_to_project[future] = project_name

            total_projects = len(project_names)
            completed_projects = 0
            
            if self.progress_callback:
                self.progress_callback(completed_projects, total_projects)

            for future in as_completed(future_to_project):
                project_name = future_to_project[future]
                try:
                    # Calculate timeout in seconds (0 means no timeout)
                    timeout_seconds = self.config.max_project_time_minutes * 60 if self.config.max_project_time_minutes > 0 else None
                    
                    result = future.result(timeout=timeout_seconds)
                    if result is None: continue
                    
                    _, df_repo = result
                    if df_repo.empty:
                        continue

                    mode = "a" if output_exists else "w"
                    header = not output_exists
                    
                    # Use proper CSV quoting to handle special characters like quotes, commas, newlines
                    df_repo.to_csv(
                        self.config.output_csv, 
                        mode=mode, 
                        header=header, 
                        index=False,
                        quoting=1,  # csv.QUOTE_ALL - quote all fields
                        escapechar='\\',  # escape character for quotes within quotes
                        doublequote=True  # double quotes to escape quotes
                    )
                    output_exists = True
                    
                    print(f"  [OUTPUT] Added {len(df_repo)} rows for {project_name}")

                except TimeoutError:
                    print(f"[TIMEOUT] Project {project_name} exceeded time limit of {self.config.max_project_time_minutes} minutes. Skipping...")
                    future.cancel()
                except Exception as e:
                    print(f"[ERROR] Worker for {project_name} failed: {e}")
                finally:
                    completed_projects += 1
                    if self.progress_callback:
                        self.progress_callback(completed_projects, total_projects)


        except KeyboardInterrupt:
            print("\n[SAFE EXIT] KeyboardInterrupt received.")
        finally:
            executor.shutdown(wait=True)
