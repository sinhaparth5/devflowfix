# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict
from datetime import datetime, timedelta
from collections import defaultdict

from app.domain.validators.base import BaseValidator, ValidationResult
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BlastRadiusValidator(BaseValidator):
    """
    Enforces rate limits to prevent runaway automation.
    
    Implements blast radius protection by limiting:
    - Maximum fixes per hour per service
    - Maximum fixes per day globally
    - Maximum concurrent remediation executions
    - Cooling-off periods after failures
    
    This prevents the system from making too many changes
    too quickly, which could cause cascading failures.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize validator.
        
        Args:
            settings: Application settings (injected dependency)
        """
        self.settings = settings or Settings()
        
        # In-memory tracking (TODO: Move to Redis for distributed tracking)
        self._hourly_fixes: Dict[str, list[datetime]] = defaultdict(list)
        self._daily_fixes: list[datetime] = []
        self._concurrent_executions: int = 0
        self._last_failure_times: Dict[str, datetime] = {}
    
    async def validate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> ValidationResult:
        """
        Validate blast radius limits.
        
        Args:
            incident: Incident to validate
            plan: Remediation plan (optional, for context)
            
        Returns:
            ValidationResult indicating if within blast radius limits
        """
        logger.info(
            "blast_radius_validation_start",
            incident_id=incident.incident_id,
            service=incident.get_service_name(),
        )
        
        result = ValidationResult(passed=True, message="Blast radius validation")
        
        self._cleanup_old_entries()
        
        checks = [
            self._check_hourly_limit(incident),
            self._check_daily_limit(),
            self._check_concurrent_limit(),
            self._check_cooling_period(incident),
            self._check_service_health_score(incident),
        ]
        
        for check in checks:
            result.add_check(check)
        
        result.passed = all(
            check.passed for check in checks if check.severity == "error"
        )
        
        if not result.passed:
            logger.warning(
                "blast_radius_limit_exceeded",
                incident_id=incident.incident_id,
                failed_checks=[c.name for c in result.get_failed_checks()],
            )
        
        return result
    
    def record_execution_start(self, incident: Incident) -> None:
        """
        Record that an execution has started.
        
        Args:
            incident: Incident being remediated
        """
        service = incident.get_service_name() or "unknown"
        now = datetime.utcnow()
        
        self._hourly_fixes[service].append(now)
        
        self._daily_fixes.append(now)
        
        self._concurrent_executions += 1
        
        logger.info(
            "blast_radius_execution_recorded",
            incident_id=incident.incident_id,
            service=service,
            concurrent_executions=self._concurrent_executions,
        )
    
    def record_execution_end(self, incident: Incident, success: bool) -> None:
        """
        Record that an execution has ended.
        
        Args:
            incident: Incident that was remediated
            success: Whether remediation succeeded
        """
        service = incident.get_service_name() or "unknown"
        
        self._concurrent_executions = max(0, self._concurrent_executions - 1)
        
        if not success:
            self._last_failure_times[service] = datetime.utcnow()
        
        logger.info(
            "blast_radius_execution_ended",
            incident_id=incident.incident_id,
            service=service,
            success=success,
            concurrent_executions=self._concurrent_executions,
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
    
    def _check_hourly_limit(self, incident: Incident):
        """Check if hourly limit per service would be exceeded."""
        service = incident.get_service_name() or "unknown"
        max_per_hour = self.settings.max_fixes_per_hour
        
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_fixes = [
            ts for ts in self._hourly_fixes.get(service, [])
            if ts > one_hour_ago
        ]
        
        current_count = len(recent_fixes)
        
        if current_count >= max_per_hour:
            return self._create_check(
                name="hourly_limit",
                passed=False,
                message=f"Service {service} has {current_count}/{max_per_hour} fixes in last hour",
                severity="error",
                service=service,
                current_count=current_count,
                max_allowed=max_per_hour,
            )
        
        return self._create_check(
            name="hourly_limit",
            passed=True,
            message=f"Service {service} has {current_count}/{max_per_hour} fixes in last hour",
            service=service,
            current_count=current_count,
            max_allowed=max_per_hour,
        )
    
    def _check_daily_limit(self):
        """Check if daily global limit would be exceeded."""
        max_per_day = self.settings.max_fixes_per_day
        
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        recent_fixes = [ts for ts in self._daily_fixes if ts > one_day_ago]
        
        current_count = len(recent_fixes)
        
        if current_count >= max_per_day:
            return self._create_check(
                name="daily_limit",
                passed=False,
                message=f"Global daily limit reached: {current_count}/{max_per_day} fixes",
                severity="error",
                current_count=current_count,
                max_allowed=max_per_day,
            )
        
        if current_count >= max_per_day * 0.8:
            return self._create_check(
                name="daily_limit",
                passed=True,
                message=f"Approaching daily limit: {current_count}/{max_per_day} fixes",
                severity="warning",
                current_count=current_count,
                max_allowed=max_per_day,
            )
        
        return self._create_check(
            name="daily_limit",
            passed=True,
            message=f"Daily limit OK: {current_count}/{max_per_day} fixes",
            current_count=current_count,
            max_allowed=max_per_day,
        )
    
    def _check_concurrent_limit(self):
        """Check if concurrent execution limit would be exceeded."""
        max_concurrent = self.settings.max_concurrent_remediations
        
        if self._concurrent_executions >= max_concurrent:
            return self._create_check(
                name="concurrent_limit",
                passed=False,
                message=f"Concurrent limit reached: {self._concurrent_executions}/{max_concurrent} executions",
                severity="error",
                current_count=self._concurrent_executions,
                max_allowed=max_concurrent,
            )
        
        return self._create_check(
            name="concurrent_limit",
            passed=True,
            message=f"Concurrent executions OK: {self._concurrent_executions}/{max_concurrent}",
            current_count=self._concurrent_executions,
            max_allowed=max_concurrent,
        )
    
    def _check_cooling_period(self, incident: Incident):
        """
        Check if service is in cooling-off period after recent failure.
        
        After a failed remediation, wait before trying again.
        """
        service = incident.get_service_name() or "unknown"
        
        if service not in self._last_failure_times:
            return self._create_check(
                name="cooling_period",
                passed=True,
                message=f"No recent failures for {service}",
                service=service,
            )
        
        last_failure = self._last_failure_times[service]
        cooling_period = timedelta(minutes=15)  
        time_since_failure = datetime.utcnow() - last_failure
        
        if time_since_failure < cooling_period:
            remaining = cooling_period - time_since_failure
            return self._create_check(
                name="cooling_period",
                passed=False,
                message=f"Service {service} in cooling period ({remaining.seconds}s remaining)",
                severity="error",
                service=service,
                remaining_seconds=remaining.seconds,
            )
        
        return self._create_check(
            name="cooling_period",
            passed=True,
            message=f"Cooling period expired for {service}",
            service=service,
        )
    
    def _check_service_health_score(self, incident: Incident):
        """
        Check service health score to prevent fixing unhealthy services.
        
        TODO: Integrate with monitoring system for actual health metrics.
        """
        service = incident.get_service_name() or "unknown"
        
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_fixes = [
            ts for ts in self._hourly_fixes.get(service, [])
            if ts > one_hour_ago
        ]
        
        fix_count = len(recent_fixes)
        
        if fix_count >= 5:  
            return self._create_check(
                name="service_health_score",
                passed=False,
                message=f"Service {service} appears unhealthy ({fix_count} recent fixes)",
                severity="warning",
                service=service,
                recent_fix_count=fix_count,
            )
        
        return self._create_check(
            name="service_health_score",
            passed=True,
            message=f"Service {service} health acceptable",
            service=service,
            recent_fix_count=fix_count,
        )
    
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
            "concurrent_executions": self._concurrent_executions,
            "max_concurrent": self.settings.max_concurrent_remediations,
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
        self._concurrent_executions = 0
        self._last_failure_times.clear()
        logger.info("blast_radius_statistics_reset")
