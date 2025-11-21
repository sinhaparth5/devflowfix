# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub Client Usage Examples

Demonstrates how to use the GitHubClient for various operations.
"""

import asyncio
from app.adapters.external.github.client import GitHubClient
from app.core.config import Settings


async def example_get_workflow_run():
    """Example: Get workflow run details."""
    async with GitHubClient() as client:
        run = await client.get_workflow_run(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        
        print(f"Workflow: {run['name']}")
        print(f"Status: {run['status']}")
        print(f"Conclusion: {run['conclusion']}")
        print(f"URL: {run['html_url']}")


async def example_rerun_failed_jobs():
    """Example: Rerun failed jobs in a workflow."""
    async with GitHubClient() as client:
        run = await client.get_workflow_run(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        
        if run['conclusion'] == 'failure':
            print(f"Workflow failed, rerunning failed jobs...")
            
            await client.rerun_failed_jobs(
                owner="myorg",
                repo="myrepo",
                run_id=123456789,
            )
            
            print("✓ Failed jobs requeued")


async def example_list_failed_workflows():
    """Example: List recent failed workflows."""
    async with GitHubClient() as client:
        runs = await client.list_workflow_runs(
            owner="myorg",
            repo="myrepo",
            status="failure",
            per_page=10,
        )
        
        print(f"Found {len(runs)} failed workflow runs:")
        for run in runs:
            print(f"  - {run['name']} (#{run['run_number']}): {run['html_url']}")


async def example_download_logs():
    """Example: Download job logs for analysis."""
    async with GitHubClient() as client:
        jobs = await client.list_jobs_for_workflow_run(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        
        failed_jobs = [job for job in jobs if job['conclusion'] == 'failure']
        
        print(f"Found {len(failed_jobs)} failed jobs")
        
        for job in failed_jobs:
            print(f"\nDownloading logs for job: {job['name']}")
            
            logs = await client.download_job_logs(
                owner="myorg",
                repo="myrepo",
                job_id=job['id'],
            )
            
            print(f"Log size: {len(logs)} bytes")


async def example_with_custom_token():
    """Example: Use custom GitHub token."""
    client = GitHubClient(token="ghp_your_token_here")
    
    try:
        run = await client.get_workflow_run(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        print(f"Run status: {run['status']}")
    finally:
        await client.close()


async def example_rate_limit_check():
    """Example: Check rate limit status."""
    async with GitHubClient() as client:
        rate_limit = await client.get_rate_limit()
        
        core = rate_limit['resources']['core']
        print(f"Rate limit: {core['remaining']}/{core['limit']}")
        print(f"Resets at: {core['reset']}")
        
        cb_status = client.get_circuit_breaker_status()
        print(f"\nCircuit breaker state: {cb_status['state']}")
        print(f"Total requests: {cb_status['total_requests']}")
        print(f"Total failures: {cb_status['total_failures']}")


async def example_error_handling():
    """Example: Error handling with retries."""
    async with GitHubClient(max_retries=3) as client:
        try:
            run = await client.get_workflow_run(
                owner="myorg",
                repo="myrepo",
                run_id=999999999,  
            )
        except Exception as e:
            print(f"Error after retries: {e}")


async def example_create_comment():
    """Example: Comment on a PR about remediation."""
    async with GitHubClient() as client:
        comment_body = """
##  DevFlowFix Remediation Report

**Incident ID:** `INC-12345`
**Status:** Resolved

### Actions Taken
- Reran failed jobs
- All tests passed on retry

### Root Cause
Transient network error during dependency download

---
*This is an automated message from DevFlowFix*
"""
        
        await client.create_issue_comment(
            owner="myorg",
            repo="myrepo",
            issue_number=42,
            body=comment_body,
        )
        
        print("✓ Comment posted to PR #42")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("GitHub Client Examples")
    print("=" * 60)
    
    examples = [
        ("Get Workflow Run", example_get_workflow_run),
        ("Rerun Failed Jobs", example_rerun_failed_jobs),
        ("List Failed Workflows", example_list_failed_workflows),
        ("Download Logs", example_download_logs),
        ("Custom Token", example_with_custom_token),
        ("Rate Limit Check", example_rate_limit_check),
        ("Error Handling", example_error_handling),
        ("Create Comment", example_create_comment),
    ]
    
    for name, example_func in examples:
        print(f"\n{name}")
        print("-" * 60)
        try:
            await example_func()
        except Exception as e:
            print(f"Example failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
