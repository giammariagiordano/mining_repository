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
