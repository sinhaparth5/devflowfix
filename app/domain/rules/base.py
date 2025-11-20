# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan


@dataclass
class RuleResult:
    """
    Result of a business rule evaluation.
    
    Contains whether the rule passed and details about the decision.
    """
    passed: bool
    rule_name: str
    message: str
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "rule_name": self.rule_name,
            "message": self.message,
            "reason": self.reason,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseRule(ABC):
    """
    Abstract base class for all business rules.
    
    Business rules implement domain logic to decide whether
    an incident should be auto-fixed or requires human intervention.
    Rules are composable and can be combined in a rules engine.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the rule name.
        
        Returns:
            Human-readable rule name
        """
        pass
    
    @abstractmethod
    async def evaluate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> RuleResult:
        """
        Evaluate the rule against an incident and remediation plan.
        
        Args:
            incident: The incident to evaluate
            plan: Optional remediation plan to evaluate
            
        Returns:
            RuleResult indicating if the rule passed or failed
        """
        pass
    
    def _create_result(
        self,
        passed: bool,
        message: str,
        reason: Optional[str] = None,
        **metadata,
    ) -> RuleResult:
        """
        Helper method to create a rule result.
        
        Args:
            passed: Whether the rule passed
            message: Result message
            reason: Optional reason for the decision
            **metadata: Additional metadata
            
        Returns:
            RuleResult instance
        """
        return RuleResult(
            passed=passed,
            rule_name=self.name,
            message=message,
            reason=reason,
            metadata=metadata,
        )
