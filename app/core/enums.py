# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from enum import Enum

class IncidentSource(str, Enum):
    """ Source platform that generated the incident. """
    GITHUB = "github"
    ARGOCD = "argocd"
    KUBERNETES = "kubernetes"
    GITLAB = "gitlab"
    JENKINS = "jenkins"
    MANUAL = "manual"

class Severity(str, Enum):
    """ Severity level of the incident. """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Outcome(str, Enum):
    """ Final outcome of the incident remediation. """
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    ESCALATED = "escalated"
    ROLLED_BACK = "rolled_back"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

class Fixability(str, Enum):
    """ Whether the incident can be automatically fixed. """
    AUTO = "auto"
    MANUAL = "manual"
    UNKNOWN = "unknown"

class FailureType(str, Enum):
    """ Specific type of failure detected """

    # Kubernetes failures
    IMAGE_PULL_BACKOFF = "imagepullbackoff"
    CRASH_LOOP_BACKOFF = "crashloopbackoff"
    OOM_KILLED = "oomkilled"
    EVICTED = "evicted"
    PENDING_POD = "pendingpod"

    # Build/CI failures
    BUILD_FAILURE = "buildfailure"
    TEST_FAILURE = "testfailure"
    LINT_FAILURE = "lintfailure"
    DEPENDENCY_ERROR = "dependencyerror"
    TIMEOUT_ERROR = "timeouterror"

    # Deployment failures
    SYNC_FAILED = "syncfailed"
    HEALTH_CHECK_FAILED = "healthcheckfailed"
    ROLLOUT_STUCK = "rolloutstuck"

    # Authentication/Authorization
    AUTH_EXPIRED = "authexpired"
    PERMISSION_DENIED = "permissiondenied"

    # Resource issues
    RESOURCE_EXHAUSTED = "resourceexhausted"
    DISK_FULL = "diskfull"
    RATE_LIMIT = "ratelimit"

    # Configuration
    CONFIG_ERROR = "configerror"
    INVALID_YAML = "invaliderror"
    MISSING_SECRET = "missingsecret"

    # Network
    CONNECTION_REFUSED = "connectionrefused"
    DNS_RESOLUTION = "dnsresolution"
    TIMEOUT = "timeout"

    # Generic
    UNKNOWN = "unknown"
    TRANSIENT = "transient"

class RemediationActionType(str, Enum):
    """ Type of remediation action to execute """

    # Github Actions
    GITHUB_RERUN_WORKFLOW = "github_rerun_workflow"
    GITHUB_CANCEL_WORKFLOW = "github_cancel_workflow"
    GITHUB_ROTATE_SECRET = "github_rotate_secret"
    GITHUB_UPDATE_DEPENDENCY = "github_update_dependency"

    # Kubernetes
    K8S_RESTART_POD = "k8s_restart_pod"
    K8S_SCALE_DEPLOYMENT = "k8s_scale_deployment"
    K8S_UPDATE_IMAGE = "k8s_update_image"
    K8S_ROLLBACK_DEPLOYMENT = "k8s_rollback_deployment"
    K8S_DELETE_EVICETED_PODS = "k8s_delete_evicted_pods"
    K8S_UPDATE_RESOURCE_LIMITS = "k8s_update_resouce_limits"
    K8S_UPDATE_SECRET = "k8s_update_secret"

    # ArgoCD
    ARGOCD_SYNC = "argocd_sync"
    ARGOCD_HARD_REFRESH = "argocd_hard_refresh"
    ARGOCD_ROLLBACK = "argocd_rollback"

    # Docker
    DOCKER_CLEAR_CACHE = "docker_clear_cache"
    DOCKER_REBUILD = "docker_rebuild"

    # Generic
    NOOP = "noop"
    WAIT_AND_RETRY = "wait_and_retry"
    NOTIFY_ONLY = "notify_only"

class Environment(str, Enum):
    """ Deployment environment """
    DEVELOPMENT = "dev"
    STAGING = "staging"
    PRODUCTION = "prod"
    TEST = "test"

class ConfidenceLevel(str, Enum):
    """ Human-readable confidence level categories. """
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """ Convert numeric confidence score to level """
        if score < 0.5:
            return cls.VERY_LOW
        elif score < 0.7:
            return cls.LOW
        elif score < 0.85:
            return cls.MEDIUM
        elif score < 0.95:
            return cls.HIGH
        else:
            return cls.VERY_HIGH
        
class ApprovalStatus(str, Enum):
    """ Status of human approval for remediation. """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    NOT_REQUIRED = "not_required"

class RiskLevel(str, Enum):
    """ Risk level of executing a remediation action. """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ValidationStatus(str, Enum):
    """ Status of pre/post remediation validation """
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"

class NotifcationType(str, Enum):
    """ Type of notification to send. """
    INCIDENT_DETECTED = "incident_detected"
    ANALYSIS_COMPLETE = "analysis_complete"
    REMEDIATION_STARTED = "remediation_started"
    REMEDIATION_SUCCESS = "remediation_success"
    REMEDIATION_FAILED = "remediation_failed"
    APPROVAL_REQUESTED = "approval_requested"
    ESCALATION = "escalation"
    BLAST_RADIUS_EXCEEDED = "blast_radius_exceeded"
    SYSTEM_ERROR = "system_error"

class StrategyType(str, Enum):
    """ Type of remediation decision strategy. """
    CONSERVATIVE = "conservative"
    SLACK_FIRST = "slack_first"
    VECTOR_DB = "vector_db"
    HYBRID = "hybrid"
    AGGRESSIVE = "aggressive"

class LogLevel(str, Enum):
    """ Logging levels. """
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class CacheStrategy(str, Enum):
    """ Caching strategy for embedding and API responses. """
    NONE = "none"
    MEMORY = "memory"
    REDIS = "redis"
    HYBRID = "hybrid"

class MetricType(str, Enum):
    """ Types of metrics tracked. """
    INCIDENT_COUNT = "incident_count"
    REMEDIATION_SUCCESS_RATE = "remediation_success_rate"
    AVERATE_RESOLUTION_TIME = "averate_resolution_time"
    CONFIDENCE_DISTRIBUTION = "confidence_distribution"
    FALSE_POSITIVE_RATE = "false_positive_rate"
    COST_PER_INCIDENT = "cost_per_incident"
    TIME_SAVED = "time_saved"

# Helper functions for enum operations

def get_all_failure_types() -> list[str]:
    """ Get list of all failure type values. """
    return [ft.value for ft in FailureType]

def get_all_remediation_actions() -> list[str]:
    """ get list of all remediation actions values. """
    return [action.value for action in RemediationActionType]

def is_critical_severity(severity: Severity) -> bool:
    """ Check if severity is critical or high """
    return severity in [Severity.CRITICAL, Severity.HIGH]

def requires_approval(
        confidence: float,
        severity: Severity,
        environment: Environment
) -> bool:
    """
    Determine if remediation requires human approval

    Args:
        confidence: Confidence score (0.0 - 1.0)
        severity: Incident severity
        environment: Deployment environment

    Returns:
        True if human approval is required 
    """
    # Always require approval for critical incidents in production
    if environment == Environment.PRODUCTION and severity == Severity.CRITICAL:
        return True
    
    # Require approval for low confidence in production
    if environment == Environment.PRODUCTION and confidence < 0.95:
        return True

    # No approval needed in dev/test
    if environment in [Environment.DEVELOPMENT, Environment.TEST]:
        return False
    
    # Staging: require approval for medium/low confidence
    if environment == Environment.STAGING and confidence < 0.85:
        return True
    
    return False

def get_confidence_threshold(environment: Environment) -> float:
    """
    Get minimum confidence threshold for auto-fix by environment

    Args:
        environment: Deployment environment
    
    Returns:
        Minimum confidence score required for auto-fix 
    """
    thresholds = {
        Environment.DEVELOPMENT: 0.70,
        Environment.TEST: 0.70,
        Environment.STAGING: 0.85,
        Environment.PRODUCTION: 0.95,
    }
    return thresholds.get(environment, 0.95)

def map_failure_to_action(failure_type: FailureType) -> RemediationActionType:
    """
    Map failure type to recommended remediation action.

    Args:
        failure_type: Type of failure detected

    Returns:
        Recommended remediation action type
    """
    mapping = {
        FailureType.IMAGE_PULL_BACKOFF: RemediationActionType.K8S_RESTART_POD,
        FailureType.CRASH_LOOP_BACKOFF: RemediationActionType.K8S_RESTART_POD,
        FailureType.OOM_KILLED: RemediationActionType.K8S_UPDATE_RESOURCE_LIMITS,
        FailureType.SYNC_FAILED: RemediationActionType.ARGOCD_SYNC,
        FailureType.BUILD_FAILURE: RemediationActionType.GITHUB_RERUN_WORKFLOW,
        FailureType.TEST_FAILURE: RemediationActionType.GITHUB_RERUN_WORKFLOW,
        FailureType.AUTH_EXPIRED: RemediationActionType.GITHUB_ROTATE_SECRET,
        FailureType.TRANSIENT: RemediationActionType.WAIT_AND_RETRY,
    }

    return mapping.get(failure_type, RemediationActionType.NOTIFY_ONLY)