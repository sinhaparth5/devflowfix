# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub Actions Adapter Usage Examples

Demonstrates how to use GitHubActionsAdapter for workflow remediation.
"""

import asyncio
from app.adapters.external.github.actions import GitHubActionsAdapter, WorkflowConclusion
from app.exceptions import RemediationTimeoutError


async def example_rerun_and_wait():
    """Example: Rerun workflow and wait for completion."""
    async with GitHubActionsAdapter() as adapter:
        result = await adapter.rerun_workflow(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
            wait_for_completion=True,
            timeout=300.0,
            poll_interval=10.0, 
            rerun_failed_only=True,
        )
        
        if result["success"]:
            print("✓ Workflow succeeded!")
            print(f"  Duration: {result['duration']:.1f}s")
            print(f"  URL: {result['url']}")
        else:
            print("✗ Workflow failed")
            print(f"  Reason: {result['failure_reason']}")
            print(f"  Failed jobs: {result['failed_job_count']}")


async def example_rerun_without_waiting():
    """Example: Trigger rerun without waiting."""
    async with GitHubActionsAdapter() as adapter:
        result = await adapter.rerun_workflow(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
            wait_for_completion=False,
        )
        
        print(f"Workflow rerun triggered: {result['url']}")
        print("Not waiting for completion...")


async def example_wait_for_existing_run():
    """Example: Wait for an already running workflow."""
    async with GitHubActionsAdapter() as adapter:
        try:
            result = await adapter.wait_for_completion(
                owner="myorg",
                repo="myrepo",
                run_id=123456789,
                timeout=600.0,  
                poll_interval=15.0,
            )
            
            print(f"Workflow completed: {result['conclusion']}")
            
        except RemediationTimeoutError as e:
            print(f"Timeout waiting for workflow: {e}")


async def example_check_success():
    """Example: Check if a workflow succeeded."""
    async with GitHubActionsAdapter() as adapter:
        success = await adapter.check_workflow_success(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        
        if success:
            print("✓ Workflow is successful")
        else:
            print("✗ Workflow failed or not complete")


async def example_get_workflow_logs():
    """Example: Download logs from failed jobs."""
    async with GitHubActionsAdapter() as adapter:
        logs = await adapter.get_workflow_logs(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
            failed_only=True,
        )
        
        print(f"Downloaded logs from {len(logs)} failed jobs")
        
        for job_id, log_content in logs.items():
            print(f"\nJob {job_id}:")
            print(f"  Log size: {len(log_content)} bytes")
            if "ERROR" in log_content:
                print("  Contains ERROR messages")


async def example_get_status_summary():
    """Example: Get comprehensive workflow status."""
    async with GitHubActionsAdapter() as adapter:
        summary = await adapter.get_workflow_status_summary(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        
        print(f"Workflow: {summary['workflow_name']}")
        print(f"Run #{summary['run_number']}")
        print(f"Status: {summary['status']}")
        print(f"Conclusion: {summary['conclusion']}")
        print(f"\nJobs:")
        print(f"  Total: {summary['total_jobs']}")
        print(f"  Succeeded: {summary['success_count']}")
        print(f"  Failed: {summary['failure_count']}")
        print(f"\nURL: {summary['url']}")


async def example_cancel_workflow():
    """Example: Cancel a running workflow."""
    async with GitHubActionsAdapter() as adapter:
        result = await adapter.cancel_workflow(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
        )
        
        if result["cancelled"]:
            print(f"✓ Workflow {result['run_id']} cancelled")


async def example_complete_remediation_workflow():
    """Example: Complete workflow remediation with error handling."""
    async with GitHubActionsAdapter() as adapter:
        owner = "myorg"
        repo = "myrepo"
        run_id = 123456789
        
        print(f"Starting remediation for workflow run {run_id}...")
        
        print("\n1. Checking current status...")
        summary = await adapter.get_workflow_status_summary(owner, repo, run_id)
        print(f"   Current status: {summary['status']}")
        print(f"   Current conclusion: {summary['conclusion']}")
        
        if summary['conclusion'] == WorkflowConclusion.FAILURE.value:
            print("\n2. Downloading logs from failed jobs...")
            logs = await adapter.get_workflow_logs(owner, repo, run_id, failed_only=True)
            print(f"   Downloaded {len(logs)} log files")
            
            for job_id, log_content in logs.items():
                if "connection timeout" in log_content.lower():
                    print(f"   Job {job_id}: Detected transient network error")
        
        print("\n3. Rerunning failed jobs...")
        result = await adapter.rerun_workflow(
            owner=owner,
            repo=repo,
            run_id=run_id,
            wait_for_completion=True,
            timeout=600.0,
            rerun_failed_only=True,
        )
        
        print("\n4. Remediation Results:")
        if result["success"]:
            print(f"   ✓ SUCCESS")
            print(f"   Duration: {result['duration']:.1f}s")
            print(f"   All jobs passed on retry")
        else:
            print(f"   ✗ FAILED")
            print(f"   Reason: {result['failure_reason']}")
            print(f"   Failed jobs: {result['failed_job_count']}/{result['total_jobs']}")
            print(f"   Manual intervention required")
        
        print(f"\n   URL: {result['url']}")


async def example_with_custom_client():
    """Example: Use adapter with custom client configuration."""
    from app.adapters.external.github.client import GitHubClient
    
    client = GitHubClient(
        token="ghp_custom_token",
        timeout=60.0,
        max_retries=5,
    )
    
    adapter = GitHubActionsAdapter(client=client)
    
    try:
        result = await adapter.rerun_workflow(
            owner="myorg",
            repo="myrepo",
            run_id=123456789,
            wait_for_completion=True,
        )
        print(f"Result: {result['success']}")
    finally:
        await adapter.close()


async def example_parallel_reruns():
    """Example: Rerun multiple workflows in parallel."""
    async with GitHubActionsAdapter() as adapter:
        workflow_runs = [
            ("myorg", "repo1", 111111),
            ("myorg", "repo2", 222222),
            ("myorg", "repo3", 333333),
        ]
        
        tasks = [
            adapter.rerun_workflow(
                owner=owner,
                repo=repo,
                run_id=run_id,
                wait_for_completion=True,
                timeout=300.0,
            )
            for owner, repo, run_id in workflow_runs
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (owner, repo, run_id), result in zip(workflow_runs, results):
            if isinstance(result, Exception):
                print(f"✗ {repo} (run {run_id}): {result}")
            elif result["success"]:
                print(f"✓ {repo} (run {run_id}): Success in {result['duration']:.1f}s")
            else:
                print(f"✗ {repo} (run {run_id}): {result['failure_reason']}")


async def main():
    """Run all examples."""
    print("=" * 70)
    print("GitHub Actions Adapter Examples")
    print("=" * 70)
    
    examples = [
        ("Rerun and Wait", example_rerun_and_wait),
        ("Rerun Without Waiting", example_rerun_without_waiting),
        ("Wait for Existing Run", example_wait_for_existing_run),
        ("Check Success", example_check_success),
        ("Get Workflow Logs", example_get_workflow_logs),
        ("Get Status Summary", example_get_status_summary),
        ("Cancel Workflow", example_cancel_workflow),
        ("Complete Remediation Workflow", example_complete_remediation_workflow),
        ("With Custom Client", example_with_custom_client),
        ("Parallel Reruns", example_parallel_reruns),
    ]
    
    for name, example_func in examples:
        print(f"\n{name}")
        print("-" * 70)
        try:
            await example_func()
        except Exception as e:
            print(f"Example failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
