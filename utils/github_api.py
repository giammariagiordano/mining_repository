# github_api.py

import time
import requests


def get_github_repo_stats(project_name: str,
                          github_token: str  = None,
                          max_retries: int = 3) -> tuple[int, int]:
    """
    Returns (stars, forks) for a GitHub repo using the REST API.
    Handles rate limiting and temporary errors with retries/backoff.
    """
    url = f"https://api.github.com/repos/{project_name}"
    base_headers = {"Accept": "application/vnd.github+json"}
    backoff = 5

    for attempt in range(1, max_retries + 1):
        headers = dict(base_headers)
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as e:
            print(
                f"[GITHUB] Attempt {attempt}/{max_retries} failed for {project_name}: "
                f"network error: {e}"
            )
            if attempt < max_retries:
                print(f"          Retrying in {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2
                continue
            else:
                print("[GITHUB] Max attempts reached, using stars=forks=0.")
                return 0, 0

        status = resp.status_code
        body_snippet = resp.text[:200]

        if status == 200:
            try:
                data = resp.json()
                stars = int(data.get("stargazers_count", 0))
                forks = int(data.get("forks_count", 0))
                return stars, forks
            except Exception as e:
                print(
                    f"[GITHUB] JSON parsing error for {project_name}: {e}. "
                    "Using stars=forks=0."
                )
                return 0, 0

        print(
            f"[GITHUB] Attempt {attempt}/{max_retries} for {project_name} failed: "
            f"HTTP {status} - {body_snippet}"
        )

        if status in (401, 403) and "bad credentials" in body_snippet.lower():
            print(
                "[GITHUB] GitHub token appears to be invalid (Bad credentials). "
                "Check --github-token or GITHUB_TOKEN."
            )
            return 0, 0

        rate_limited = False
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            rate_limited = True
        if "rate limit" in body_snippet.lower():
            rate_limited = True

        if rate_limited:
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            wait_seconds = backoff
            if reset_ts:
                try:
                    reset_ts = int(reset_ts)
                    now = int(time.time())
                    wait_seconds = max(reset_ts - now, 0)
                    wait_seconds = min(wait_seconds, 300)
                except Exception:
                    wait_seconds = backoff
            if attempt < max_retries:
                print(
                    f"[GITHUB] Likely rate limited for {project_name}. "
                    f"Sleeping {wait_seconds} seconds before retry..."
                )
                time.sleep(wait_seconds)
                backoff *= 2
                continue
            else:
                print(
                    "[GITHUB] Still rate-limited after retries, using stars=forks=0."
                )
                return 0, 0

        if attempt < max_retries:
            print(f"[GITHUB] Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2
            continue
        else:
            print("[GITHUB] Max attempts reached, using stars=forks=0.")
            return 0, 0


def get_issue_body(project_name: str,
                   issue_number: str,
                   github_token: str = None,
                   max_retries: int = 3) -> str:
    """
    Returns the body of a GitHub issue using the REST API.
    Handles rate limiting and temporary errors with retries/backoff.
    """
    url = f"https://api.github.com/repos/{project_name}/issues/{issue_number}"
    base_headers = {"Accept": "application/vnd.github+json"}
    backoff = 5

    for attempt in range(1, max_retries + 1):
        headers = dict(base_headers)
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as e:
            print(
                f"[GITHUB] Attempt {attempt}/{max_retries} failed for {project_name}#{issue_number}: "
                f"network error: {e}"
            )
            if attempt < max_retries:
                print(f"          Retrying in {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2
                continue
            else:
                print("[GITHUB] Max attempts reached, returning empty body.")
                return ""

        status = resp.status_code
        body_snippet = resp.text[:200]

        if status == 200:
            try:
                data = resp.json()
                return data.get("body") or ""
            except Exception as e:
                print(
                    f"[GITHUB] JSON parsing error for {project_name}#{issue_number}: {e}. "
                    "Returning empty body."
                )
                return ""

        print(
            f"[GITHUB] Attempt {attempt}/{max_retries} for {project_name}#{issue_number} failed: "
            f"HTTP {status} - {body_snippet}"
        )

        if status in (401, 403) and "bad credentials" in body_snippet.lower():
            print(
                "[GITHUB] GitHub token appears to be invalid (Bad credentials). "
                "Check --github-token or GITHUB_TOKEN."
            )
            return ""

        rate_limited = False
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            rate_limited = True
        if "rate limit" in body_snippet.lower():
            rate_limited = True

        if rate_limited:
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            wait_seconds = backoff
            if reset_ts:
                try:
                    reset_ts = int(reset_ts)
                    now = int(time.time())
                    wait_seconds = max(reset_ts - now, 0)
                    wait_seconds = min(wait_seconds, 300)
                except Exception:
                    wait_seconds = backoff
            if attempt < max_retries:
                print(
                    f"[GITHUB] Likely rate limited for {project_name}. "
                    f"Sleeping {wait_seconds} seconds before retry..."
                )
                time.sleep(wait_seconds)
                backoff *= 2
                continue
            else:
                print(
                    "[GITHUB] Still rate-limited after retries, returning empty body."
                )
                return ""

        if attempt < max_retries:
            print(f"[GITHUB] Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2
            continue
        else:
            print("[GITHUB] Max attempts reached, returning empty body.")
            return ""
    return ""


def get_issue_comments(project_name: str,
                       issue_number: str,
                       github_token: str = None,
                       max_retries: int = 3) -> list[dict]:
    """
    Returns the comments of a GitHub issue using the REST API.
    Each comment is a dict with 'user', 'created_at', and 'body'.
    Handles rate limiting and temporary errors with retries/backoff.
    """
    url = f"https://api.github.com/repos/{project_name}/issues/{issue_number}/comments"
    base_headers = {"Accept": "application/vnd.github+json"}
    backoff = 5

    for attempt in range(1, max_retries + 1):
        headers = dict(base_headers)
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as e:
            print(
                f"[GITHUB] Attempt {attempt}/{max_retries} failed for {project_name}#{issue_number} comments: "
                f"network error: {e}"
            )
            if attempt < max_retries:
                print(f"          Retrying in {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2
                continue
            else:
                print("[GITHUB] Max attempts reached, returning empty comments.")
                return []

        status = resp.status_code
        body_snippet = resp.text[:200]

        if status == 200:
            try:
                data = resp.json()
                comments = []
                for comment in data:
                    comments.append({
                        "user": comment.get("user", {}).get("login", "unknown"),
                        "created_at": comment.get("created_at", ""),
                        "body": comment.get("body", "")
                    })
                return comments
            except Exception as e:
                print(
                    f"[GITHUB] JSON parsing error for {project_name}#{issue_number} comments: {e}. "
                    "Returning empty comments."
                )
                return []

        print(
            f"[GITHUB] Attempt {attempt}/{max_retries} for {project_name}#{issue_number} comments failed: "
            f"HTTP {status} - {body_snippet}"
        )

        if status in (401, 403) and "bad credentials" in body_snippet.lower():
            print(
                "[GITHUB] GitHub token appears to be invalid (Bad credentials). "
                "Check --github-token or GITHUB_TOKEN."
            )
            return []

        rate_limited = False
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            rate_limited = True
        if "rate limit" in body_snippet.lower():
            rate_limited = True

        if rate_limited:
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            wait_seconds = backoff
            if reset_ts:
                try:
                    reset_ts = int(reset_ts)
                    now = int(time.time())
                    wait_seconds = max(reset_ts - now, 0)
                    wait_seconds = min(wait_seconds, 300)
                except Exception:
                    wait_seconds = backoff
            if attempt < max_retries:
                print(
                    f"[GITHUB] Likely rate limited for {project_name}. "
                    f"Sleeping {wait_seconds} seconds before retry..."
                )
                time.sleep(wait_seconds)
                backoff *= 2
                continue
            else:
                print(
                    "[GITHUB] Still rate-limited after retries, returning empty comments."
                )
                return []

        if attempt < max_retries:
            print(f"[GITHUB] Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2
            continue
        else:
            print("[GITHUB] Max attempts reached, returning empty comments.")
            return []
    return []


def get_all_issues(project_name: str,
                   github_token: str = None,
                   state: str = "all",
                   max_retries: int = 3) -> list[dict]:
    """
    Returns all issues from a GitHub repository using the REST API with pagination.
    
    Args:
        project_name: Repository name (e.g., "owner/repo")
        github_token: GitHub API token
        state: "open", "closed", or "all"
        max_retries: Number of retry attempts
    
    Returns:
        List of issues, each with: number, title, state, body, created_at, closed_at, user, comments_count
    """
    all_issues = []
    page = 1
    per_page = 100  # Max allowed by GitHub API
    
    base_headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        base_headers["Authorization"] = f"Bearer {github_token}"
    
    while True:
        url = f"https://api.github.com/repos/{project_name}/issues"
        params = {
            "state": state,
            "page": page,
            "per_page": per_page,
            "sort": "created",
            "direction": "desc"
        }
        
        backoff = 5
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, headers=base_headers, params=params, timeout=15)
            except requests.RequestException as e:
                print(f"[GITHUB] Attempt {attempt}/{max_retries} failed for {project_name} issues page {page}: {e}")
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    return all_issues
            
            status = resp.status_code
            
            if status == 200:
                try:
                    data = resp.json()
                    if not data:  # No more issues
                        return all_issues
                    
                    for issue in data:
                        # Skip pull requests (they appear in issues endpoint)
                        if "pull_request" in issue:
                            continue
                        
                        all_issues.append({
                            "number": issue.get("number"),
                            "title": issue.get("title", ""),
                            "state": issue.get("state", ""),
                            "body": issue.get("body", ""),
                            "created_at": issue.get("created_at", ""),
                            "closed_at": issue.get("closed_at", ""),
                            "user": issue.get("user", {}).get("login", "unknown"),
                            "comments_count": issue.get("comments", 0),
                            "labels": [label.get("name", "") for label in issue.get("labels", [])]
                        })
                    
                    page += 1
                    break  # Success, go to next page
                    
                except Exception as e:
                    print(f"[GITHUB] JSON parsing error for {project_name} issues: {e}")
                    return all_issues
            
            # Handle rate limiting
            if status in (403, 429):
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    reset_ts = resp.headers.get("X-RateLimit-Reset")
                    if reset_ts:
                        try:
                            wait_seconds = max(int(reset_ts) - int(time.time()), 0)
                            wait_seconds = min(wait_seconds, 300)
                            print(f"[GITHUB] Rate limited. Waiting {wait_seconds} seconds...")
                            time.sleep(wait_seconds)
                            continue
                        except Exception:
                            pass
            
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            else:
                return all_issues
    
    return all_issues
