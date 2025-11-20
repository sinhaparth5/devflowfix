# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional

from app.domain.rules.base import BaseRule, RuleResult
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import Environment, Severity
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ConfidenceRule(BaseRule):
    """
    Validates confidence thresholds based on environment and severity.
    
    Different environments have different confidence requirements:
    - Production: 95% confidence required
    - Staging: 85% confidence required
    - Development: 70% confidence required
    
    Critical severity incidents may have higher thresholds.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the confidence rule.
        
        Args:
            settings: Application settings (injected dependency)
        """
        self.settings = settings or Settings()
    
    @property
    def name(self) -> str:
        """Get the rule name."""
        return "ConfidenceThresholdRule"
    
    async def evaluate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> RuleResult:
        """
        Evaluate if incident confidence meets threshold.
        
        Args:
            incident: Incident to evaluate
            plan: Remediation plan (optional)
            
        Returns:
            RuleResult indicating if confidence is sufficient
        """
        logger.info(
            "confidence_rule_evaluate_start",
            incident_id=incident.incident_id,
            confidence=incident.confidence,
        )
        
        if incident.confidence is None:
            return self._create_result(
                passed=False,
                message="Confidence score not available",
                reason="Cannot evaluate without confidence score",
            )
        
        env_str = incident.context.get("environment", "prod")
        environment = self._parse_environment(env_str)
        
        threshold = self._get_threshold(environment, incident.severity)
        
        passed = incident.confidence >= threshold
        
        if passed:
            logger.info(
                "confidence_rule_passed",
                incident_id=incident.incident_id,
                confidence=incident.confidence,
                threshold=threshold,
            )
            return self._create_result(
                passed=True,
                message=f"Confidence {incident.confidence:.2%} meets threshold {threshold:.2%}",
                confidence=incident.confidence,
                threshold=threshold,
                environment=environment.value,
            )
        else:
            logger.warning(
                "confidence_rule_failed",
                incident_id=incident.incident_id,
                confidence=incident.confidence,
                threshold=threshold,
            )
            return self._create_result(
                passed=False,
                message=f"Confidence {incident.confidence:.2%} below threshold {threshold:.2%}",
                reason=f"Requires {threshold:.2%} confidence for {environment.value} environment",
                confidence=incident.confidence,
                threshold=threshold,
                environment=environment.value,
            )
    
    def _parse_environment(self, env_str: str) -> Environment:
        """
        Parse environment string to Environment enum.
        
        Args:
            env_str: Environment string (prod, staging, dev, etc.)
            
        Returns:
            Environment enum value
        """
        env_map = {
            "prod": Environment.PRODUCTION,
            "production": Environment.PRODUCTION,
            "staging": Environment.STAGING,
            "stage": Environment.STAGING,
            "dev": Environment.DEVELOPMENT,
            "development": Environment.DEVELOPMENT,
            "test": Environment.TEST,
        }
        return env_map.get(env_str.lower(), Environment.PRODUCTION)
    
    def _get_threshold(self, environment: Environment, severity: Severity) -> float:
        """
        Get confidence threshold based on environment and severity.
        
        Args:
            environment: Deployment environment
            severity: Incident severity
            
        Returns:
            Confidence threshold (0.0 - 1.0)
        """
        base_thresholds = {
            Environment.PRODUCTION: self.settings.production_confidence_threshold,
            Environment.STAGING: self.settings.high_confidence_threshold,
            Environment.DEVELOPMENT: self.settings.min_confidence_threshold,
            Environment.TEST: self.settings.min_confidence_threshold,
        }
        
        threshold = base_thresholds.get(environment, 0.95)
        
        if environment == Environment.PRODUCTION and severity == Severity.CRITICAL:
            threshold = max(threshold, 0.98)  
        
        return threshold
    
    def get_threshold_for_environment(self, environment: Environment) -> float:
        """
        Get the confidence threshold for a specific environment.
        
        Args:
            environment: Target environment
            
        Returns:
            Confidence threshold
        """
        return self._get_threshold(environment, Severity.MEDIUM)
