# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Any, List
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

from app.core.enums import Environment, LogLevel


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    
    url: str = Field(default="postgresql://postgres:postgres@localhost:5432/devflowfix", alias="DATABASE_URL")
    pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    pool_recycle: int = Field(default=3600, alias="DB_POOL_RECYCLE")
    pool_pre_ping: bool = Field(default=True, alias="DB_POOL_PRE_PING")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class GitHubSettings(BaseSettings):
    """GitHub integration configuration."""
    
    webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    app_id: Optional[str] = Field(default=None, alias="GITHUB_APP_ID")
    app_private_key_path: Optional[str] = Field(default=None, alias="GITHUB_APP_PRIVATE_KEY_PATH")
    app_installation_id: Optional[str] = Field(default=None, alias="GITHUB_APP_INSTALLATION_ID")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class AWSSettings(BaseSettings):
    """AWS configuration."""
    
    region: str = Field(default="us-east-1", alias="AWS_REGION")
    lambda_function_name: Optional[str] = Field(default=None, alias="AWS_LAMBDA_FUNCTION_NAME")
    account_id: Optional[str] = Field(default=None, alias="AWS_ACCOUNT_ID")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class AISettings(BaseSettings):
    """AI/ML configuration."""
    
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    nvidia_api_key: Optional[str] = Field(default=None, alias="NVIDIA_API_KEY")
    embedding_model: str = Field(default="nvidia/nv-embed-v1", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=768, alias="EMBEDDING_DIMENSIONS")
    llm_model: str = Field(default="gpt-4-turbo-preview", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2000, alias="LLM_MAX_TOKENS")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class RedisSettings(BaseSettings):
    """Redis configuration."""
    
    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    ttl: int = Field(default=3600, alias="REDIS_TTL")
    max_connections: int = Field(default=10, alias="REDIS_MAX_CONNECTIONS")
    socket_timeout: int = Field(default=5, alias="REDIS_SOCKET_TIMEOUT")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class ObservabilitySettings(BaseSettings):
    """Observability and monitoring configuration."""
    
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")
    datadog_api_key: Optional[str] = Field(default=None, alias="DATADOG_API_KEY")
    xray_enabled: bool = Field(default=False, alias="XRAY_ENABLED")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class SecuritySettings(BaseSettings):
    """Security configuration."""
    
    secret_key: str = Field(default="change-me-in-production-use-secrets-manager", alias="SECRET_KEY")
    jwt_secret_key: str = Field(default="change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, alias="JWT_EXPIRATION_HOURS")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class FeatureFlagSettings(BaseSettings):
    """Feature flags configuration."""
    
    enable_auto_remediation: bool = Field(default=True, alias="ENABLE_AUTO_REMEDIATION")
    enable_slack_notifications: bool = Field(default=True, alias="ENABLE_SLACK_NOTIFICATIONS")
    enable_pagerduty_escalation: bool = Field(default=False, alias="ENABLE_PAGERDUTY_ESCALATION")
    enable_metrics_collection: bool = Field(default=True, alias="ENABLE_METRICS_COLLECTION")
    enable_learning_mode: bool = Field(default=True, alias="ENABLE_LEARNING_MODE")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class ConfidenceSettings(BaseSettings):
    """Confidence threshold configuration."""
    
    threshold_dev: float = Field(default=0.70, alias="CONFIDENCE_THRESHOLD_DEV")
    threshold_staging: float = Field(default=0.85, alias="CONFIDENCE_THRESHOLD_STAGING")
    threshold_prod: float = Field(default=0.95, alias="CONFIDENCE_THRESHOLD_PROD")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""
    
    enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    requests: int = Field(default=100, alias="RATE_LIMIT_REQUESTS")
    window: int = Field(default=60, alias="RATE_LIMIT_WINDOW")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class Settings(BaseSettings):
    """
    Main application settings loaded from environment variables.
    
    All settings can be overridden by environment variables.
    Environment variables should be prefixed with the setting name in uppercase.
    
    Example:
        DATABASE_URL=postgresql://user:pass@localhost:5432/db
        ENVIRONMENT=production
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application settings
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment (dev, staging, prod)"
    )
    
    app_name: str = Field(default="DevFlowFix", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    version: str = Field(default="0.1.0", description="Application version")
    
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level"
    )
    
    debug: bool = Field(default=False, description="Enable debug mode", alias="DEBUG")
    
    # API settings
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=4, alias="API_WORKERS")
    
    # Database settings
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/vector_db",
        description="PostgreSQL database URL with credentials"
    )
    
    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Database connection pool size"
    )
    
    database_max_overflow: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Maximum overflow connections beyond pool_size"
    )
    
    database_pool_timeout: int = Field(
        default=30,
        ge=1,
        description="Timeout in seconds for getting connection from pool"
    )
    
    database_pool_recycle: int = Field(
        default=3600,
        ge=0,
        description="Recycle connections after this many seconds (0=disabled)"
    )
    
    # NVIDIA API settings
    nvidia_api_key: str = Field(
        default="",
        description="NVIDIA NGC API key for LLM and embedding services"
    )
    
    nvidia_api_base_url: str = Field(
        default="https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions",
        description="NVIDIA API base URL"
    )
    
    nvidia_llm_model: str = Field(
        default="meta/llama-3.1-8b-instruct",
        description="LLM model identifier to use for analysis"
    )
    
    nvidia_embedding_model: str = Field(
        default="nvidia/nv-embed-v1",
        description="Embedding model identifier for vector generation"
    )
    
    nvidia_api_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="API request timeout in seconds"
    )
    
    nvidia_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed API calls"
    )
    
    # GitHub settings
    github_token: str = Field(
        default="",
        description="GitHub personal access token or App installation token"
    )
    
    github_webhook_secret: str = Field(
        default="",
        description="GitHub webhook secret for signature verification"
    )
    
    github_api_base_url: str = Field(
        default="https://api.github.com",
        description="GitHub API base URL"
    )
    
    # Slack settings
    slack_token: str = Field(
        default="",
        description="Slack bot token (xoxb-...)"
    )
    
    slack_signing_secret: str = Field(
        default="",
        description="Slack signing secret for request verification"
    )
    
    slack_incidents_channel: str = Field(
        default="#incidents",
        description="Slack channel for incident notifications"
    )
    
    slack_approvals_channel: str = Field(
        default="#devflowfix-approvals",
        description="Slack channel for approval requests"
    )
    
    # ArgoCD settings
    argocd_server: Optional[str] = Field(
        default=None,
        description="ArgoCD server URL (e.g., argocd.example.com)"
    )
    
    argocd_token: Optional[str] = Field(
        default=None,
        description="ArgoCD API token for authentication"
    )
    
    argocd_insecure: bool = Field(
        default=False,
        description="Skip TLS verification for ArgoCD (dev only)"
    )
    
    # Kubernetes settings
    kubeconfig_path: Optional[str] = Field(
        default=None,
        description="Path to kubeconfig file (defaults to ~/.kube/config)"
    )
    
    kubernetes_namespace: str = Field(
        default="default",
        description="Default Kubernetes namespace"
    )
    
    # PagerDuty settings
    pagerduty_api_key: Optional[str] = Field(
        default=None,
        description="PagerDuty API key for incident integration"
    )
    
    pagerduty_service_id: Optional[str] = Field(
        default=None,
        description="PagerDuty service ID"
    )
    
    # AWS settings
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for services"
    )
    
    aws_account_id: Optional[str] = Field(
        default=None,
        description="AWS account ID"
    )
    
    # Redis settings
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (redis://host:port/db)"
    )
    
    redis_max_connections: int = Field(
        default=10,
        ge=1,
        description="Maximum Redis connection pool size"
    )
    
    redis_socket_timeout: int = Field(
        default=5,
        ge=1,
        description="Redis socket timeout in seconds"
    )
    
    # Confidence thresholds
    min_confidence_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for any auto-fix consideration"
    )
    
    high_confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Threshold for high confidence classification"
    )
    
    production_confidence_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Required confidence for production auto-fix"
    )
    
    # Blast radius limits
    max_fixes_per_hour: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum auto-fixes per hour per service"
    )
    
    max_fixes_per_day: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum auto-fixes per day per service"
    )
    
    max_concurrent_remediations: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent remediation executions"
    )
    
    # Embedding settings
    embedding_dimension: int = Field(
        default=768,
        description="Vector embedding dimension size"
    )
    
    # Remediation settings
    remediation_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Remediation execution timeout in seconds"
    )
    
    remediation_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed remediation"
    )
    
    enable_rollback: bool = Field(
        default=True,
        description="Enable automatic rollback on remediation failure"
    )
    
    rollback_snapshot_ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Time-to-live for rollback snapshots in hours"
    )
    
    # Approval settings
    approval_timeout_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="Approval request timeout in minutes"
    )
    
    require_approval_for_production: bool = Field(
        default=True,
        description="Always require approval for production remediations"
    )
    
    # RAG settings
    rag_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of similar incidents to retrieve for RAG"
    )
    
    rag_similarity_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for RAG retrieval"
    )
    
    rag_max_context_length: int = Field(
        default=4000,
        ge=1000,
        le=16000,
        description="Maximum context length for RAG in tokens"
    )
    
    # CORS settings
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins (use specific origins in production)"
    )
    
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    
    # Rate limiting settings
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    
    rate_limit_requests_per_minute: int = Field(
        default=60,
        ge=1,
        le=1000,
        description="Rate limit: requests per minute per client"
    )
    
    rate_limit_requests_per_hour: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Rate limit: requests per hour per client"
    )
    
    # Feature flags
    enable_slack_rag: bool = Field(
        default=True,
        description="Enable RAG retrieval from Slack conversations"
    )
    
    enable_auto_fix: bool = Field(
        default=True,
        description="Enable automatic remediation execution"
    )
    
    enable_metrics: bool = Field(
        default=True,
        description="Enable metrics collection and reporting"
    )
    
    enable_tracing: bool = Field(
        default=False,
        description="Enable distributed tracing (AWS X-Ray)"
    )
    
    enable_learning: bool = Field(
        default=True,
        description="Enable learning from feedback"
    )
    
    enable_webhooks: bool = Field(
        default=True,
        description="Enable webhook endpoints"
    )
    
    # Security settings
    secret_key: str = Field(
        default="change-me-in-production-use-secrets-manager",
        description="Secret key for signing tokens (use AWS Secrets Manager in prod)"
    )
    
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    
    jwt_expiration_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="JWT token expiration in minutes"
    )
    
    # Metrics settings
    metrics_export_interval_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Interval for exporting metrics"
    )
    
    # Logging settings
    log_format: str = Field(
        default="json",
        description="Log format: json or console"
    )
    
    log_to_file: bool = Field(
        default=False,
        description="Enable logging to file"
    )
    
    log_file_path: str = Field(
        default="/var/log/devflowfix/app.log",
        description="Log file path when log_to_file is enabled"
    )
    
    # Validators
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise ValueError("Database URL must start with postgresql://")
        return v
    
    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v: Any) -> Environment:
        """Ensure environment is valid."""
        if isinstance(v, str):
            return Environment(v.lower())
        return v
    
    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: Any) -> LogLevel:
        """Ensure log level is valid."""
        if isinstance(v, str):
            return LogLevel(v.upper())
        return v
    
    # Properties
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT
    
    @property
    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return self.environment == Environment.STAGING
    
    @property
    def confidence_threshold(self) -> float:
        """
        Get confidence threshold based on environment.
        
        Returns:
            Confidence threshold for current environment
        """
        if self.is_production:
            return self.production_confidence_threshold
        elif self.is_staging:
            return self.high_confidence_threshold
        else:
            return self.min_confidence_threshold
    
    @property
    def database(self) -> DatabaseSettings:
        """Get database settings."""
        return DatabaseSettings()
    
    @property
    def github(self) -> GitHubSettings:
        """Get GitHub settings."""
        return GitHubSettings()
    
    @property
    def aws(self) -> AWSSettings:
        """Get AWS settings."""
        return AWSSettings()
    
    @property
    def ai(self) -> AISettings:
        """Get AI settings."""
        return AISettings()
    
    @property
    def redis(self) -> RedisSettings:
        """Get Redis settings."""
        return RedisSettings()
    
    @property
    def observability(self) -> ObservabilitySettings:
        """Get observability settings."""
        return ObservabilitySettings()
    
    @property
    def security(self) -> SecuritySettings:
        """Get security settings."""
        return SecuritySettings()
    
    @property
    def features(self) -> FeatureFlagSettings:
        """Get feature flags."""
        return FeatureFlagSettings()
    
    @property
    def confidence(self) -> ConfidenceSettings:
        """Get confidence thresholds."""
        return ConfidenceSettings()
    
    @property
    def rate_limit(self) -> RateLimitSettings:
        """Get rate limit settings."""
        return RateLimitSettings()
    
    # Methods
    def get_blast_radius_limit(self, time_window: str = "hour") -> int:
        """
        Get blast radius limit based on time window.
        
        Args:
            time_window: "hour" or "day"
            
        Returns:
            Maximum number of fixes allowed
        """
        if time_window == "hour":
            return self.max_fixes_per_hour
        elif time_window == "day":
            return self.max_fixes_per_day
        else:
            return self.max_fixes_per_hour
    
    def requires_approval(
        self,
        confidence: float,
        environment: Optional[Environment] = None,
    ) -> bool:
        """
        Determine if remediation requires human approval.
        
        Args:
            confidence: Confidence score (0.0 - 1.0)
            environment: Target environment (defaults to current)
            
        Returns:
            True if approval is required
        """
        env = environment or self.environment
        
        # Always require approval in production if configured
        if env == Environment.PRODUCTION and self.require_approval_for_production:
            return True
        
        # Require approval if confidence below threshold
        threshold = self.confidence_threshold
        if confidence < threshold:
            return True
        
        return False
    
    def get_database_url_safe(self) -> str:
        """
        Get database URL with credentials masked for logging.
        
        Returns:
            Database URL with password masked
        """
        if "@" in self.database_url:
            # Split and mask password
            parts = self.database_url.split("@")
            credentials = parts[0].split("://")[1]
            if ":" in credentials:
                user = credentials.split(":")[0]
                masked = f"{self.database_url.split('://')[0]}://{user}:***@{parts[1]}"
                return masked
        return self.database_url


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    This function is cached to ensure settings are only loaded once.
    
    Returns:
        Settings instance
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Reload settings from environment.
    
    Useful for testing or hot-reloading configuration.
    
    Returns:
        New Settings instance
    """
    get_settings.cache_clear()
    return get_settings()


# Global settings instance
settings = get_settings()