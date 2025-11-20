# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict
from datetime import datetime, timedelta
from collections import defaultdict

from app.domain.rules.base import BaseRule, RuleResult
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BlastRadiusRule(BaseRule):
    """
    Enforces blast radius limits to prevent runaway automation.
    
    Limits:
    - Maximum 10 fixes per hour per service (configurable)
    - Maximum 50 fixes per day globally (configurable)
    - Cooling period after failures
    
    This prevents the system from making too many changes too quickly,
    which could cause cascading failures or mask underlying issues.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the blast radius rule.
        
        Args:
            settings: Application settings (injected dependency)
        """
        self.settings = settings or Settings()
        
        # In-memory tracking (TODO: Move to Redis for distributed systems)
        self._hourly_fixes: Dict[str, list[datetime]] = defaultdict(list)
        self._daily_fixes: list[datetime] = []
        self._last_failure_times: Dict[str, datetime] = {}
    
    @property
    def name(self) -> str:
        """Get the rule name."""
        return "BlastRadiusRule"
    
    async def evaluate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> RuleResult:
        """
        Evaluate if blast radius limits would be exceeded.
        
        Args:
            incident: Incident to evaluate
            plan: Remediation plan (optional)
            
        Returns:
            RuleResult indicating if within blast radius limits
        """
        logger.info(
            "blast_radius_rule_evaluate_start",
            incident_id=incident.incident_id,
            service=incident.get_service_name(),
        )
        
        self._cleanup_old_entries()
        
        service = incident.get_service_name() or "unknown"
        
        hourly_check = self._check_hourly_limit(service)
        if not hourly_check["passed"]:
            return self._create_result(
                passed=False,
                message=hourly_check["message"],
                reason="Hourly rate limit exceeded for service",
                service=service,
                current_count=hourly_check["current_count"],
                max_allowed=hourly_check["max_allowed"],
            )
        
        daily_check = self._check_daily_limit()
        if not daily_check["passed"]:
            return self._create_result(
                passed=False,
                message=daily_check["message"],
                reason="Daily global rate limit exceeded",
                current_count=daily_check["current_count"],
                max_allowed=daily_check["max_allowed"],
            )
        
        cooling_check = self._check_cooling_period(service)
        if not cooling_check["passed"]:
            return self._create_result(
                passed=False,
                message=cooling_check["message"],
                reason="Service in cooling period after recent failure",
                service=service,
                remaining_seconds=cooling_check["remaining_seconds"],
            )
        
        logger.info(
            "blast_radius_rule_passed",
            incident_id=incident.incident_id,
            service=service,
        )
        
        return self._create_result(
            passed=True,
            message="Within blast radius limits",
            service=service,
            hourly_count=hourly_check["current_count"],
            daily_count=daily_check["current_count"],
        )
    
    def record_execution(self, incident: Incident) -> None:
        """
        Record that a remediation execution occurred.
        
        Args:
            incident: Incident being remediated
        """
        service = incident.get_service_name() or "unknown"
        now = datetime.utcnow()
        
        self._hourly_fixes[service].append(now)
        
        self._daily_fixes.append(now)
        
        logger.info(
            "blast_radius_execution_recorded",
            incident_id=incident.incident_id,
            service=service,
        )
    
    def record_failure(self, incident: Incident) -> None:
        """
        Record that a remediation failed.
        
        Args:
            incident: Incident that failed remediation
        """
        service = incident.get_service_name() or "unknown"
        self._last_failure_times[service] = datetime.utcnow()
        
        logger.info(
            "blast_radius_failure_recorded",
            incident_id=incident.incident_id,
            service=service,
        )
    
    def _cleanup_old_entries(self) -> None:
        """Remove tracking entries older than retention period."""
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)
        
        for service in list(self._hourly_fixes.keys()):
            self._hourly_fixes[service] = [
                ts for ts in self._hourly_fixes[service]
                if ts > one_hour_ago
            ]
            if not self._hourly_fixes[service]:
                del self._hourly_fixes[service]
        
        self._daily_fixes = [
            ts for ts in self._daily_fixes
            if ts > one_day_ago
        ]
        
        for service in list(self._last_failure_times.keys()):
            if self._last_failure_times[service] < one_day_ago:
                del self._last_failure_times[service]
    
    def _check_hourly_limit(self, service: str) -> dict:
        """Check hourly limit for a service."""
        max_per_hour = self.settings.max_fixes_per_hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        recent_fixes = [
            ts for ts in self._hourly_fixes.get(service, [])
            if ts > one_hour_ago
        ]
        
        current_count = len(recent_fixes)
        passed = current_count < max_per_hour
        
        return {
            "passed": passed,
            "current_count": current_count,
            "max_allowed": max_per_hour,
            "message": (
                f"Service {service}: {current_count}/{max_per_hour} fixes in last hour"
                if passed
                else f"Service {service} exceeded hourly limit: {current_count}/{max_per_hour}"
            ),
        }
    
    def _check_daily_limit(self) -> dict:
        """Check daily global limit."""
        max_per_day = self.settings.max_fixes_per_day
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        
        recent_fixes = [
            ts for ts in self._daily_fixes
            if ts > one_day_ago
        ]
        
        current_count = len(recent_fixes)
        passed = current_count < max_per_day
        
        return {
            "passed": passed,
            "current_count": current_count,
            "max_allowed": max_per_day,
            "message": (
                f"Global: {current_count}/{max_per_day} fixes in last 24 hours"
                if passed
                else f"Global daily limit exceeded: {current_count}/{max_per_day}"
            ),
        }
    
    def _check_cooling_period(self, service: str) -> dict:
        """Check if service is in cooling period after failure."""
        if service not in self._last_failure_times:
            return {
                "passed": True,
                "remaining_seconds": 0,
                "message": f"No recent failures for {service}",
            }
        
        last_failure = self._last_failure_times[service]
        cooling_period = timedelta(minutes=15)  
        time_since_failure = datetime.utcnow() - last_failure
        
        if time_since_failure < cooling_period:
            remaining = cooling_period - time_since_failure
            return {
                "passed": False,
                "remaining_seconds": int(remaining.total_seconds()),
                "message": f"Service {service} in cooling period ({remaining.seconds}s remaining)",
            }
        
        return {
            "passed": True,
            "remaining_seconds": 0,
            "message": f"Cooling period expired for {service}",
        }
    
    def get_statistics(self) -> dict:
        """
        Get current blast radius statistics.
        
        Returns:
            Dictionary with current counts and limits
        """
        self._cleanup_old_entries()
        
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        
        return {
            "hourly_fixes_by_service": {
                service: len([ts for ts in times if ts > one_hour_ago])
                for service, times in self._hourly_fixes.items()
            },
            "total_daily_fixes": len([ts for ts in self._daily_fixes if ts > one_day_ago]),
            "max_hourly_per_service": self.settings.max_fixes_per_hour,
            "max_daily_global": self.settings.max_fixes_per_day,
            "services_in_cooling_period": list(self._last_failure_times.keys()),
        }
    
    def reset_statistics(self) -> None:
        """Reset all statistics. Useful for testing."""
        self._hourly_fixes.clear()
        self._daily_fixes.clear()
        self._last_failure_times.clear()
        logger.info("blast_radius_statistics_reset")
