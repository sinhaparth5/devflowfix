# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan


@dataclass
class ValidationCheck:
    """
    Individual validation check result.
    
    Represents a single check performed during validation.
    """
    name: str
    passed: bool
    message: str
    severity: str = "info"  
    metadata: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    """
    Result of a validation operation.
    
    Contains overall pass/fail status and individual check results.
    """
    passed: bool
    message: Optional[str] = None
    checks: list[ValidationCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def add_check(self, check: ValidationCheck) -> None:
        """Add a validation check result."""
        self.checks.append(check)
    
    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)
    
    def has_errors(self) -> bool:
        """Check if any checks failed with error severity."""
        return any(
            not check.passed and check.severity == "error"
            for check in self.checks
        )
    
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0 or any(
            check.severity == "warning" for check in self.checks
        )
    
    def get_failed_checks(self) -> list[ValidationCheck]:
        """Get all failed validation checks."""
        return [check for check in self.checks if not check.passed]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "message": self.message,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "message": check.message,
                    "severity": check.severity,
                    "metadata": check.metadata,
                }
                for check in self.checks
            ],
            "warnings": self.warnings,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseValidator(ABC):
    """
    Abstract base class for all validators.
    
    Validators implement the Strategy pattern to perform
    different types of validation checks.
    """
    
    @abstractmethod
    async def validate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> ValidationResult:
        """
        Perform validation.
        
        Args:
            incident: The incident to validate
            plan: Optional remediation plan to validate
            
        Returns:
            ValidationResult with pass/fail status and details
        """
        pass
    
    def _create_check(
        self,
        name: str,
        passed: bool,
        message: str,
        severity: str = "info",
        **metadata,
    ) -> ValidationCheck:
        """
        Helper method to create a validation check.
        
        Args:
            name: Check name
            passed: Whether check passed
            message: Check message
            severity: Check severity (info, warning, error)
            **metadata: Additional metadata
            
        Returns:
            ValidationCheck instance
        """
        return ValidationCheck(
            name=name,
            passed=passed,
            message=message,
            severity=severity,
            metadata=metadata,
        )
