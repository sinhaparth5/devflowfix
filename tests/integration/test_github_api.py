#!/usr/bin/env python3
# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - GitHub API Integration Test

import os
import sys
from datetime import datetime

def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_result(test_name, passed, message=""):
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"  {status}: {test_name}")
    if message:
        print(f"          {message}")

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
    
    def add(self, name, passed, message=""):
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print_result(name, passed, message)
    
    def summary(self):
        print("\n" + "-" * 60)
        print(f"  SUMMARY: {self.passed} passed, {self.failed} failed")
        print("-" * 60)

results = TestResults()


def test_github_token():
    """Test if GitHub token is configured"""
    token = os.getenv("GITHUB_TOKEN")
    
    if token:
        masked = token[:4] + "*" * (len(token) - 8) + token[-4:]
        results.add("GitHub token configured", True, f"Token: {masked}")
        return token
    else:
        results.add("GitHub token configured", False, "GITHUB_TOKEN not set")
        return None


def test_github_authentication(token):
    """Test GitHub API authentication"""
    if not token:
        results.add("GitHub authentication", False, "No token available")
        return None
    
    try:
        import httpx
        
        response = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10.0,
        )
        
        if response.status_code == 200:
            data = response.json()
            username = data.get("login", "unknown")
            results.add("GitHub authentication", True, f"Authenticated as: {username}")
            return data
        elif response.status_code == 401:
            results.add("GitHub authentication", False, "Invalid or expired token")
            return None
        else:
            results.add("GitHub authentication", False, f"Status: {response.status_code}")
            return None
            
    except Exception as e:
        results.add("GitHub authentication", False, str(e))
        return None


def test_github_rate_limit(token):
    """Test GitHub API rate limit status"""
    if not token:
        results.add("GitHub rate limit", False, "No token available")
        return
    
    try:
        import httpx
        
        response = httpx.get(
            "https://api.github.com/rate_limit",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10.0,
        )
        
        if response.status_code == 200:
            data = response.json()
            core = data["resources"]["core"]
            remaining = core["remaining"]
            limit = core["limit"]
            reset_time = datetime.fromtimestamp(core["reset"])
            
            results.add(
                "GitHub rate limit", 
                True, 
                f"Remaining: {remaining}/{limit}, Resets: {reset_time.strftime('%H:%M:%S')}"
            )
        else:
            results.add("GitHub rate limit", False, f"Status: {response.status_code}")
            
    except Exception as e:
        results.add("GitHub rate limit", False, str(e))


def test_github_repos(token):
    """Test listing repositories"""
    if not token:
        results.add("List repositories", False, "No token available")
        return
    
    try:
        import httpx
        
        response = httpx.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            params={"per_page": 5, "sort": "updated"},
            timeout=10.0,
        )
        
        if response.status_code == 200:
            repos = response.json()
            repo_names = [r["full_name"] for r in repos[:3]]
            results.add(
                "List repositories", 
                True, 
                f"Found {len(repos)} repos. Recent: {', '.join(repo_names)}"
            )
        else:
            results.add("List repositories", False, f"Status: {response.status_code}")
            
    except Exception as e:
        results.add("List repositories", False, str(e))


def test_github_workflow_runs(token):
    """Test fetching workflow runs (requires repo access)"""
    if not token:
        results.add("Workflow runs API", False, "No token available")
        return
    
    try:
        import httpx
        
        # First get a repo
        response = httpx.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            params={"per_page": 1, "sort": "updated"},
            timeout=10.0,
        )
        
        if response.status_code != 200 or not response.json():
            results.add("Workflow runs API", False, "No repositories found")
            return
        
        repo = response.json()[0]["full_name"]
        
        # Try to get workflow runs
        response = httpx.get(
            f"https://api.github.com/repos/{repo}/actions/runs",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            params={"per_page": 5},
            timeout=10.0,
        )
        
        if response.status_code == 200:
            data = response.json()
            total = data.get("total_count", 0)
            runs = data.get("workflow_runs", [])
            
            if runs:
                latest = runs[0]
                status = latest.get("conclusion") or latest.get("status")
                results.add(
                    "Workflow runs API", 
                    True, 
                    f"Repo: {repo}, Total runs: {total}, Latest: {status}"
                )
            else:
                results.add("Workflow runs API", True, f"Repo: {repo}, No workflow runs")
        elif response.status_code == 404:
            results.add("Workflow runs API", True, "API accessible (no Actions in repo)")
        else:
            results.add("Workflow runs API", False, f"Status: {response.status_code}")
            
    except Exception as e:
        results.add("Workflow runs API", False, str(e))


def test_github_webhooks_api(token):
    """Test webhook-related API access"""
    if not token:
        results.add("Webhooks API", False, "No token available")
        return
    
    try:
        import httpx
        
        # Get user's repos to check webhook access
        response = httpx.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            params={"per_page": 1, "type": "owner"},
            timeout=10.0,
        )
        
        if response.status_code != 200 or not response.json():
            results.add("Webhooks API", False, "No owned repositories")
            return
        
        repo = response.json()[0]["full_name"]
        
        # Try to list webhooks (requires admin access)
        response = httpx.get(
            f"https://api.github.com/repos/{repo}/hooks",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10.0,
        )
        
        if response.status_code == 200:
            hooks = response.json()
            results.add("Webhooks API", True, f"Repo: {repo}, Webhooks: {len(hooks)}")
        elif response.status_code == 404:
            results.add("Webhooks API", True, "API accessible (needs admin scope)")
        else:
            results.add("Webhooks API", False, f"Status: {response.status_code}")
            
    except Exception as e:
        results.add("Webhooks API", False, str(e))


def test_github_scopes(token):
    """Check what scopes the token has"""
    if not token:
        results.add("Token scopes", False, "No token available")
        return
    
    try:
        import httpx
        
        response = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10.0,
        )
        
        if response.status_code == 200:
            scopes = response.headers.get("X-OAuth-Scopes", "none")
            results.add("Token scopes", True, f"Scopes: {scopes}")
        else:
            results.add("Token scopes", False, f"Status: {response.status_code}")
            
    except Exception as e:
        results.add("Token scopes", False, str(e))


def main():
    print("\n" + "🐙 " * 20)
    print("  GitHub API Integration Test")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🐙 " * 20)
    
    print_header("Configuration")
    token = test_github_token()
    
    print_header("Authentication")
    user_data = test_github_authentication(token)
    test_github_scopes(token)
    
    print_header("API Access")
    test_github_rate_limit(token)
    test_github_repos(token)
    
    print_header("CI/CD Features")
    test_github_workflow_runs(token)
    test_github_webhooks_api(token)
    
    results.summary()
    
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())