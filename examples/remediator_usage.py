# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Base Remediator Usage Examples

Demonstrates how to create and use remediators.
"""

import asyncio
from datetime import datetime
from app.domain.remediators.base import BaseRemediator
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import (
    RemediationActionType,
    RiskLevel,
    IncidentSource,
    Severity,
    FailureType,
)


class NoOpRemediator(BaseRemediator):
    """
    No-operation remediator for testing.
    
    Always succeeds without doing anything.
    """
    
    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.NOOP
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """Execute no-op remediation."""
        self._log_execution_start(incident, plan)
        
        await asyncio.sleep(0.1)
        
        result = self._create_success_result(
            message="No-op remediation completed successfully",
            duration_seconds=0,
            actions_performed=["noop"],
        )
        
        self._log_execution_complete(incident, result)
        return result


class GitHubRerunRemediator(BaseRemediator):
    """
    Remediator that reruns GitHub Actions workflows.
    
    Requires parameters:
    - owner: Repository owner
    - repo: Repository name
    - run_id: Workflow run ID
    """
    
    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.GITHUB_RERUN_WORKFLOW
    
    def validate_parameters(self, plan: RemediationPlan) -> None:
        """Validate required parameters."""
        required = ["owner", "repo", "run_id"]
        
        for param in required:
            if not plan.get_parameter(param):
                raise ValueError(f"Missing required parameter: {param}")
        
        run_id = plan.get_parameter("run_id")
        if not isinstance(run_id, int):
            raise ValueError(f"run_id must be an integer, got {type(run_id)}")
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """Execute GitHub workflow rerun."""
        self._log_execution_start(incident, plan)
        start_time = datetime.now()
        
        try:
            self.validate_parameters(plan)
        except ValueError as e:
            return self._create_failure_result(
                message="Parameter validation failed",
                error_message=str(e),
            )
        
        owner = plan.get_parameter("owner")
        repo = plan.get_parameter("repo")
        run_id = plan.get_parameter("run_id")
        
        try:
            self.logger.info(
                "github_rerun_workflow",
                owner=owner,
                repo=repo,
                run_id=run_id,
            )
            
            await asyncio.sleep(0.5)  
            
            duration = (datetime.now() - start_time).seconds
            result = self._create_success_result(
                message=f"Successfully reran workflow {run_id} for {owner}/{repo}",
                duration_seconds=duration,
                actions_performed=[
                    f"Triggered rerun of workflow {run_id}",
                    "Workflow completed successfully",
                ],
                metadata={
                    "owner": owner,
                    "repo": repo,
                    "run_id": run_id,
                    "workflow_url": f"https://github.com/{owner}/{repo}/actions/runs/{run_id}",
                },
            )
            
            self._log_execution_complete(incident, result)
            return result
        
        except Exception as e:
            duration = (datetime.now() - start_time).seconds
            result = self._create_failure_result(
                message="Failed to rerun GitHub workflow",
                error_message=str(e),
                duration_seconds=duration,
                actions_performed=[f"Attempted to rerun workflow {run_id}"],
            )
            
            self._log_execution_complete(incident, result)
            return result


class KubernetesRestartPodRemediator(BaseRemediator):
    """
    Remediator that restarts Kubernetes pods.
    
    Only handles Kubernetes-sourced incidents with specific failure types.
    """
    
    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.K8S_RESTART_POD
    
    def can_handle(self, incident: Incident, plan: RemediationPlan) -> bool:
        """Check if this remediator can handle the incident."""
        if not super().can_handle(incident, plan):
            return False
        
        if incident.source != IncidentSource.KUBERNETES:
            return False
        
        valid_failures = [
            FailureType.CRASH_LOOP_BACKOFF,
            FailureType.IMAGE_PULL_BACKOFF,
            FailureType.PENDING_POD,
        ]
        
        return incident.failure_type in valid_failures
    
    def validate_parameters(self, plan: RemediationPlan) -> None:
        """Validate required parameters."""
        required = ["namespace", "pod_name"]
        
        for param in required:
            if not plan.get_parameter(param):
                raise ValueError(f"Missing required parameter: {param}")
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """Execute pod restart."""
        self._log_execution_start(incident, plan)
        start_time = datetime.now()
        
        try:
            self.validate_parameters(plan)
        except ValueError as e:
            return self._create_failure_result(
                message="Parameter validation failed",
                error_message=str(e),
            )
        
        namespace = plan.get_parameter("namespace")
        pod_name = plan.get_parameter("pod_name")
        
        try:
            self.logger.info(
                "k8s_restart_pod",
                namespace=namespace,
                pod_name=pod_name,
            )
            
            await asyncio.sleep(1.0) 
            
            duration = (datetime.now() - start_time).seconds
            result = self._create_success_result(
                message=f"Successfully restarted pod {pod_name} in namespace {namespace}",
                duration_seconds=duration,
                actions_performed=[
                    f"Deleted pod {pod_name}",
                    "Waited for new pod to start",
                    "Verified pod is running",
                ],
                metadata={
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "new_pod_name": f"{pod_name}-abc123",
                },
            )
            
            self._log_execution_complete(incident, result)
            return result
        
        except Exception as e:
            duration = (datetime.now() - start_time).seconds
            result = self._create_failure_result(
                message="Failed to restart pod",
                error_message=str(e),
                duration_seconds=duration,
                rollback_required=False,
            )
            
            self._log_execution_complete(incident, result)
            return result


async def example_basic_usage():
    """Example: Basic remediator usage."""
    print("\n" + "=" * 70)
    print("Example 1: Basic Remediator Usage")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_test_001",
        source=IncidentSource.GITHUB,
        severity=Severity.MEDIUM,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed",
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.NOOP,
        risk_level=RiskLevel.LOW,
    )
    
    remediator = NoOpRemediator()
    result = await remediator.execute(incident, plan)
    
    print(f"Success: {result.success}")
    print(f"Outcome: {result.outcome}")
    print(f"Message: {result.message}")
    print(f"Actions: {result.actions_performed}")


async def example_with_parameters():
    """Example: Remediator with parameters."""
    print("\n" + "=" * 70)
    print("Example 2: GitHub Rerun Remediator")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_test_002",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Workflow run failed",
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    plan.add_parameter("owner", "myorg")
    plan.add_parameter("repo", "myrepo")
    plan.add_parameter("run_id", 123456789)
    
    remediator = GitHubRerunRemediator()
    result = await remediator.execute(incident, plan)
    
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")
    print(f"Duration: {result.duration_seconds}s")
    print(f"Actions performed:")
    for action in result.actions_performed:
        print(f"  - {action}")
    print(f"Metadata: {result.metadata}")


async def example_validation_failure():
    """Example: Parameter validation failure."""
    print("\n" + "=" * 70)
    print("Example 3: Parameter Validation Failure")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_test_003",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    
    remediator = GitHubRerunRemediator()
    result = await remediator.execute(incident, plan)
    
    print(f"Success: {result.success}")
    print(f"Error: {result.error_message}")


async def example_can_handle():
    """Example: Using can_handle method."""
    print("\n" + "=" * 70)
    print("Example 4: can_handle() Method")
    print("=" * 70)
    
    k8s_incident = Incident(
        incident_id="inc_test_004",
        source=IncidentSource.KUBERNETES,
        failure_type=FailureType.CRASH_LOOP_BACKOFF,
    )
    
    github_incident = Incident(
        incident_id="inc_test_005",
        source=IncidentSource.GITHUB,
        failure_type=FailureType.BUILD_FAILURE,
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.K8S_RESTART_POD,
        risk_level=RiskLevel.MEDIUM,
    )
    plan.add_parameter("namespace", "default")
    plan.add_parameter("pod_name", "my-app-123")
    
    remediator = KubernetesRestartPodRemediator()
    
    can_handle_k8s = remediator.can_handle(k8s_incident, plan)
    print(f"Can handle K8s incident: {can_handle_k8s}")
    
    can_handle_github = remediator.can_handle(github_incident, plan)
    print(f"Can handle GitHub incident: {can_handle_github}")
    
    if can_handle_k8s:
        result = await remediator.execute(k8s_incident, plan)
        print(f"\nK8s remediation result: {result.success}")
        print(f"Message: {result.message}")


async def example_callable():
    """Example: Using remediator as callable."""
    print("\n" + "=" * 70)
    print("Example 5: Callable Remediator")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_test_006",
        source=IncidentSource.GITHUB,
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.NOOP,
        risk_level=RiskLevel.LOW,
    )
    
    remediator = NoOpRemediator()
    
    result = await remediator(incident, plan)
    
    print(f"Called remediator directly: {result.success}")
    print(f"Remediator: {remediator}")
    print(f"Repr: {repr(remediator)}")


async def main():
    """Run all examples."""
    examples = [
        example_basic_usage,
        example_with_parameters,
        example_validation_failure,
        example_can_handle,
        example_callable,
    ]
    
    for example in examples:
        await example()


if __name__ == "__main__":
    asyncio.run(main())
