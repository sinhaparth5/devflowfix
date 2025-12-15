# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
PR Management Configuration and Setup Example

This example demonstrates how to:
1. Configure GitHub tokens for external repositories
2. Set up automatic PR creation workflows
3. Track and monitor created PRs
4. Manage PR lifecycle through DevFlowFix

Usage:
    python setup_pr_management.py
"""

import asyncio
import httpx
from typing import Optional

# Configuration
DEVFLOWFIX_API_BASE = "http://localhost:8000/api/v1"

# External repository configurations
EXTERNAL_REPOS = [
    {
        "owner": "myorg",
        "repo": "backend-service",
        "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # GitHub Personal Access Token
        "description": "Token for backend-service auto-fix PRs",
        "scopes": ["repo", "workflow", "contents"],
    },
    {
        "owner": "myorg",
        "repo": "frontend-app",
        "token": "ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
        "description": "Token for frontend-app auto-fix PRs",
        "scopes": ["repo", "workflow", "contents"],
    },
    {
        "owner": "myorg",
        "repo": None,  # Organization-level token
        "token": "ghp_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        "description": "Organization-wide token for myorg (fallback)",
        "scopes": ["repo", "workflow", "contents"],
    },
]


async def register_github_tokens():
    """
    Register GitHub tokens for external repositories.
    
    This allows DevFlowFix to create PRs in these repos automatically.
    """
    print("\n" + "=" * 80)
    print("STEP 1: Register GitHub Tokens for External Repositories")
    print("=" * 80)
    
    async with httpx.AsyncClient() as client:
        for repo_config in EXTERNAL_REPOS:
            owner = repo_config["owner"]
            repo = repo_config.get("repo")
            
            repo_display = f"{owner}/{repo}" if repo else f"{owner}/*"
            
            print(f"\n📝 Registering token for {repo_display}...")
            
            params = {
                "owner": owner,
                "repo": repo,
                "token": repo_config["token"],
                "description": repo_config["description"],
                "scopes": ",".join(repo_config["scopes"]),
                "created_by": "setup_script",
            }
            
            try:
                response = await client.post(
                    f"{DEVFLOWFIX_API_BASE}/pr-management/tokens/register",
                    params=params,
                )
                response.raise_for_status()
                
                result = response.json()
                token_info = result.get("token", {})
                
                print(f"   ✅ Success!")
                print(f"   Token ID: {token_info.get('id')}")
                print(f"   Repository: {token_info.get('repository')}")
                print(f"   Scopes: {token_info.get('scopes')}")
                
            except httpx.HTTPError as e:
                print(f"   ❌ Failed: {e}")


async def list_registered_tokens():
    """List all registered GitHub tokens."""
    print("\n" + "=" * 80)
    print("STEP 2: List Registered Tokens")
    print("=" * 80)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{DEVFLOWFIX_API_BASE}/pr-management/tokens",
                params={"active_only": True},
            )
            response.raise_for_status()
            
            result = response.json()
            tokens = result.get("tokens", [])
            
            print(f"\n📋 Found {len(tokens)} active token(s):\n")
            
            for token in tokens:
                print(f"   Repository: {token['repository']}")
                print(f"   Token ID: {token['id']}")
                print(f"   Masked: {token['token_masked']}")
                print(f"   Scopes: {token['scopes']}")
                print(f"   Created: {token['created_at']}")
                print()
                
        except httpx.HTTPError as e:
            print(f"❌ Failed to list tokens: {e}")


async def view_pr_statistics():
    """View PR creation statistics."""
    print("\n" + "=" * 80)
    print("STEP 3: PR Creation Statistics")
    print("=" * 80)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{DEVFLOWFIX_API_BASE}/pr-management/stats",
            )
            response.raise_for_status()
            
            result = response.json()
            stats = result.get("statistics", {})
            
            print(f"\n📊 PR Statistics:\n")
            print(f"   Total PRs Created: {stats.get('total_prs', 0)}")
            print(f"   Merged PRs: {stats.get('merged_count', 0)}")
            print(f"   Merge Rate: {stats.get('merge_rate', 0):.1f}%")
            print(f"   Avg Files per PR: {stats.get('avg_files_per_pr', 0):.1f}")
            print(f"   Total Additions: {stats.get('total_additions', 0)}")
            print(f"   Total Deletions: {stats.get('total_deletions', 0)}")
            
            print(f"\n   Status Distribution:")
            statuses = stats.get('status_distribution', {})
            for status, count in statuses.items():
                print(f"      - {status}: {count}")
            
        except httpx.HTTPError as e:
            print(f"❌ Failed to retrieve statistics: {e}")


async def list_created_prs(repository: Optional[str] = None):
    """List PRs created by DevFlowFix."""
    print("\n" + "=" * 80)
    print("STEP 4: List Created PRs")
    print("=" * 80)
    
    async with httpx.AsyncClient() as client:
        params = {}
        if repository:
            params["repository"] = repository
        
        try:
            response = await client.get(
                f"{DEVFLOWFIX_API_BASE}/pr-management/pulls",
                params=params,
            )
            response.raise_for_status()
            
            result = response.json()
            prs = result.get("prs", [])
            total = result.get("total", 0)
            
            print(f"\n📋 Found {total} PR(s) (showing {len(prs)}):\n")
            
            for pr in prs:
                print(f"   PR #{pr['pr_number']}: {pr['title']}")
                print(f"      Repository: {pr['repository']}")
                print(f"      Status: {pr['status']}")
                print(f"      Failure Type: {pr['failure_type']}")
                print(f"      Confidence: {pr['confidence_score']:.0%}")
                print(f"      Branch: {pr['branch']}")
                print(f"      Files Changed: {pr['files_changed']}")
                print(f"      URL: {pr['pr_url']}")
                print()
                
        except httpx.HTTPError as e:
            print(f"❌ Failed to list PRs: {e}")


async def demonstrate_webhook_flow():
    """
    Demonstrate the complete workflow:
    1. Webhook received from external repo
    2. DevFlowFix analyzes the error
    3. NVIDIA API generates fix
    4. PR automatically created in external repo
    5. PR tracked in DevFlowFix
    """
    print("\n" + "=" * 80)
    print("STEP 5: Demonstrate Complete Webhook → Analysis → PR Workflow")
    print("=" * 80)
    
    print("""
This shows the complete automated workflow:

1. EXTERNAL REPO WORKFLOW FAILS
   └─ Repository: myorg/backend-service
   └─ Failure: Test failure in pytest
   └─ Webhook sent to DevFlowFix

2. DEVFLOWFIX RECEIVES WEBHOOK
   └─ Event: workflow_run (conclusion: failure)
   └─ Webhook endpoint: POST /api/v1/webhooks/github
   └─ Incident created in database

3. ANALYSIS STAGE
   └─ Error log extracted
   └─ Embedding generated (NVIDIA NeMo)
   └─ Vector DB searched for similar incidents
   └─ LLM analyzes root cause (NVIDIA Llama 3.1)
   └─ Confidence score calculated

4. SOLUTION GENERATION
   └─ NVIDIA API generates fix
   └─ Code changes identified
   └─ Configuration updates proposed
   └─ Prevention measures suggested

5. PR CREATION IN SOURCE REPO
   └─ GitHub token retrieved (per-repo)
   └─ New branch created: devflowfix/auto-fix-test-failure-xxxxx
   └─ Code changes committed
   └─ Configuration updated
   └─ Pull Request created with detailed explanation
   └─ PR metadata stored in DevFlowFix DB

6. PR TRACKING
   └─ PR can be viewed at: http://localhost:8000/api/v1/pr-management/pulls
   └─ Status automatically synced with GitHub
   └─ Merge history tracked
   └─ Statistics updated

Example API Calls:

List all PRs created:
  GET http://localhost:8000/api/v1/pr-management/pulls

Get PR details:
  GET http://localhost:8000/api/v1/pr-management/pulls/{pr_id}

Update PR status:
  POST http://localhost:8000/api/v1/pr-management/pulls/{pr_id}/update-status
  Body: {"new_status": "merged"}

View statistics:
  GET http://localhost:8000/api/v1/pr-management/stats

Register new token:
  POST http://localhost:8000/api/v1/pr-management/tokens/register
  Params: owner, repo, token, description, scopes

List tokens:
  GET http://localhost:8000/api/v1/pr-management/tokens
    """)


async def test_webhook_simulation():
    """
    Simulate a webhook from an external repository.
    """
    print("\n" + "=" * 80)
    print("STEP 6: Simulate Webhook from External Repository")
    print("=" * 80)
    
    # Example GitHub Actions workflow failure webhook
    webhook_payload = {
        "action": "completed",
        "workflow_run": {
            "id": 123456789,
            "name": "Tests",
            "conclusion": "failure",
            "status": "completed",
            "event": "push",
            "head_branch": "main",
            "head_commit": {
                "message": "Add new feature",
            },
        },
        "repository": {
            "name": "backend-service",
            "full_name": "myorg/backend-service",
            "owner": {
                "login": "myorg",
            },
        },
    }
    
    print(f"\n📤 Simulating webhook from: myorg/backend-service")
    print(f"   Workflow: Tests")
    print(f"   Status: Failure")
    print(f"   Run ID: 123456789")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{DEVFLOWFIX_API_BASE}/webhooks/github",
                json=webhook_payload,
                headers={
                    "X-GitHub-Event": "workflow_run",
                    "X-GitHub-Delivery": "12345-67890-12345",
                },
            )
            
            print(f"\n✅ Webhook received and processing started!")
            print(f"   Incident ID: {response.json().get('incident_id')}")
            print(f"\n   DevFlowFix will now:")
            print(f"      1. Analyze the failure")
            print(f"      2. Call NVIDIA API for solution")
            print(f"      3. Create PR in myorg/backend-service")
            print(f"      4. Track PR in database")
            
        except httpx.HTTPError as e:
            print(f"❌ Failed to send webhook: {e}")


async def main():
    """Run all setup steps."""
    print("\n" + "🚀" * 40)
    print("DevFlowFix PR Management Setup & Demo")
    print("🚀" * 40)
    
    await register_github_tokens()
    await list_registered_tokens()
    await view_pr_statistics()
    await list_created_prs()
    await demonstrate_webhook_flow()
    await test_webhook_simulation()
    
    print("\n" + "=" * 80)
    print("✅ Setup Complete!")
    print("=" * 80)
    print("""
Next Steps:

1. Start DevFlowFix:
   $ uv run uvicorn app.main:app --reload

2. Register tokens (if not done):
   POST http://localhost:8000/api/v1/pr-management/tokens/register

3. Monitor PRs via API:
   GET http://localhost:8000/api/v1/pr-management/pulls

4. Configure webhooks in GitHub:
   - Go to repo settings → Webhooks
   - Add: http://your-devflowfix-server:8000/api/v1/webhooks/github
   - Events: workflow runs, push events

5. Watch PRs get created automatically when failures occur!
    """)


if __name__ == "__main__":
    asyncio.run(main())
