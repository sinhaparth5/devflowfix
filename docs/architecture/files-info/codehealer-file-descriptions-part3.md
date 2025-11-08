# CodeHealer - Complete File Documentation (Part 3)
## Final Part: Utils, Tests, Scripts, Infrastructure, Documentation

---

## 📁 app/utils/ - Utility Functions

### **app/utils/logging.py**
**Purpose**: Structured logging setup
**Contents**:
- Configure structlog
- JSON logging for production
- Pretty logging for development
- Add request IDs, trace IDs
**Example**:
```python
import structlog

def setup_logging(environment: str = "dev"):
    """Configure structured logging"""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    
    if environment == "prod":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

# Usage:
logger = structlog.get_logger()
logger.info("incident_processed", incident_id="inc_123", confidence=0.92)
```
**Why it exists**: Structured logs for better observability

### **app/utils/retry.py**
**Purpose**: Retry decorators using tenacity
**Contents**:
- Retry with exponential backoff
- Retry on specific exceptions
- Max retry limits
**Example**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry_error_callback=lambda retry_state: None
)
async def call_external_api():
    """Retry on transient failures"""
    pass

# Custom retry decorator for specific use case
def retry_on_rate_limit(func):
    return retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, max=60),
        retry=retry_if_exception_type(RateLimitError)
    )(func)
```
**Why it exists**: Resilience against transient failures

### **app/utils/circuit_breaker.py**
**Purpose**: Circuit breaker pattern using pybreaker
**Contents**:
- Circuit breaker for external APIs
- Fail fast when service is down
- Automatic recovery
**Example**:
```python
from pybreaker import CircuitBreaker

# Create circuit breaker for GitHub API
github_breaker = CircuitBreaker(
    fail_max=5,  # Open after 5 failures
    reset_timeout=60,  # Try again after 60 seconds
    exclude=[HTTPException]  # Don't count certain exceptions
)

@github_breaker
async def call_github_api():
    """Call protected by circuit breaker"""
    pass
```
**Why it exists**: Prevent cascading failures

### **app/utils/rate_limiter.py**
**Purpose**: Rate limiting utilities
**Contents**:
- Token bucket algorithm
- Sliding window rate limiter
**Example**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/webhook")
@limiter.limit("100/minute")
async def webhook_endpoint():
    pass
```
**Why it exists**: Protect APIs from abuse

### **app/utils/datetime.py**
**Purpose**: Datetime utilities
**Contents**:
- Parse ISO datetime strings
- Convert timezones
- Calculate durations
**Example**:
```python
from datetime import datetime, timedelta

def parse_iso_datetime(date_string: str) -> datetime:
    """Parse ISO format datetime"""
    return datetime.fromisoformat(date_string.replace('Z', '+00:00'))

def calculate_duration(start: datetime, end: datetime) -> int:
    """Calculate duration in seconds"""
    return int((end - start).total_seconds())

def is_business_hours() -> bool:
    """Check if current time is during business hours"""
    now = datetime.now()
    return 9 <= now.hour < 17 and now.weekday() < 5
```
**Why it exists**: Common datetime operations

### **app/utils/hashing.py**
**Purpose**: Hash generation utilities
**Contents**:
- Generate incident IDs
- Hash embeddings for cache keys
**Example**:
```python
import hashlib
import uuid

def generate_incident_id() -> str:
    """Generate unique incident ID"""
    return f"inc_{uuid.uuid4().hex[:12]}"

def hash_text(text: str) -> str:
    """Generate hash for caching"""
    return hashlib.sha256(text.encode()).hexdigest()
```
**Why it exists**: Consistent ID/hash generation

### **app/utils/validation.py**
**Purpose**: Common validation functions
**Contents**:
- Validate URLs
- Validate tokens
- Sanitize inputs
**Example**:
```python
import re
from urllib.parse import urlparse

def is_valid_url(url: str) -> bool:
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def sanitize_log(log: str, max_length: int = 10000) -> str:
    """Sanitize log for storage"""
    # Remove secrets, truncate, etc.
    sanitized = re.sub(r'token=[a-zA-Z0-9]+', 'token=***', log)
    return sanitized[:max_length]
```
**Why it exists**: Input validation and sanitization

### **app/utils/metrics.py**
**Purpose**: Metrics helpers for CloudWatch/Prometheus
**Contents**:
- Increment counters
- Record histograms
- CloudWatch custom metrics
**Example**:
```python
from aws_embedded_metrics import metric_scope

@metric_scope
def record_incident_processed(metrics, incident: Incident):
    """Record incident processing metrics"""
    metrics.put_metric("IncidentsProcessed", 1, "Count")
    metrics.put_metric("ProcessingTime", incident.resolution_time_seconds, "Seconds")
    metrics.set_property("Source", incident.source)
    metrics.set_property("Outcome", incident.outcome)
```
**Why it exists**: CloudWatch metrics for Lambda

### **app/utils/lambda_utils.py**
**Purpose**: Lambda-specific utilities
**Contents**:
- Cold start optimization
- Global variable reuse
- Connection pooling
**Example**:
```python
# Global variables for Lambda reuse across invocations
_db_engine = None
_nvidia_client = None

def get_db_engine():
    """Get or create database engine (reuse across invocations)"""
    global _db_engine
    if _db_engine is None:
        _db_engine = create_engine(settings.database_url, poolclass=NullPool)
    return _db_engine

def get_nvidia_client():
    """Get or create NVIDIA client (reuse across invocations)"""
    global _nvidia_client
    if _nvidia_client is None:
        _nvidia_client = NVIDIAClient(api_key=settings.nvidia_api_key)
    return _nvidia_client

def warm_up():
    """Pre-warm connections during Lambda init"""
    get_db_engine()
    get_nvidia_client()
```
**Why it exists**: Optimize Lambda cold starts

---

## 📁 app/observability/ - Observability

### **app/observability/event_bus.py**
**Purpose**: Event bus for Observer pattern
**Contents**:
- Publish events
- Subscribe observers
- Async event dispatch
**Example**:
```python
class EventBus:
    def __init__(self):
        self.observers: Dict[str, List[BaseObserver]] = {}
    
    def subscribe(self, event_type: str, observer: BaseObserver):
        """Subscribe observer to event type"""
        if event_type not in self.observers:
            self.observers[event_type] = []
        self.observers[event_type].append(observer)
    
    async def publish(self, event_type: str, data: dict):
        """Publish event to all subscribers"""
        if event_type in self.observers:
            for observer in self.observers[event_type]:
                await observer.handle(event_type, data)

# Usage:
event_bus = EventBus()
event_bus.subscribe("remediation.started", MetricsObserver())
event_bus.subscribe("remediation.completed", LoggingObserver())

await event_bus.publish("remediation.started", {"incident_id": "inc_123"})
```
**Why it exists**: Decouple event producers from consumers

### **app/observability/observers/base.py**
**Purpose**: Base observer interface
**Contents**:
```python
from abc import ABC, abstractmethod

class BaseObserver(ABC):
    @abstractmethod
    async def handle(self, event_type: str, data: dict):
        """Handle event"""
        pass
```
**Why it exists**: Observer pattern interface

### **app/observability/observers/metrics.py**
**Purpose**: Metrics observer
**Contents**:
- Listen to events and record metrics
- CloudWatch metrics
**Example**:
```python
class MetricsObserver(BaseObserver):
    async def handle(self, event_type: str, data: dict):
        if event_type == "remediation.completed":
            await self.record_remediation_metric(
                success=data["success"],
                duration=data["duration"]
            )
```
**Why it exists**: Automatic metrics from events

### **app/observability/observers/logging.py**
**Purpose**: Logging observer
**Contents**: Log all events
**Why it exists**: Centralized event logging

### **app/observability/observers/alerting.py**
**Purpose**: Alerting observer
**Contents**:
- Listen for error events
- Send alerts (Slack, PagerDuty)
**Why it exists**: Automatic alerting

### **app/observability/tracing/config.py**
**Purpose**: AWS X-Ray tracing configuration
**Contents**:
- Configure X-Ray SDK
- Tracing for Lambda
- Tracing for external API calls
**Example**:
```python
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.ext.aiohttp.client import aws_xray_trace_config

xray_recorder.configure(
    service="codehealer",
    sampling=True
)

# Trace httpx requests
async with httpx.AsyncClient() as client:
    with xray_recorder.capture("nvidia_api_call"):
        response = await client.post(...)
```
**Why it exists**: Distributed tracing in AWS

### **app/observability/tracing/decorators.py**
**Purpose**: Tracing decorators
**Contents**:
- Decorator to trace functions
**Example**:
```python
from aws_xray_sdk.core import xray_recorder

def trace_function(name: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with xray_recorder.capture(name):
                return await func(*args, **kwargs)
        return wrapper
    return decorator

@trace_function("analyze_incident")
async def analyze_incident(incident: Incident):
    pass
```
**Why it exists**: Easy function tracing

### **app/observability/metrics/prometheus.py**
**Purpose**: Prometheus metrics (if used instead of CloudWatch)
**Contents**: Prometheus client setup
**Why it exists**: Alternative to CloudWatch

### **app/observability/metrics/custom.py**
**Purpose**: Custom business metrics
**Contents**:
- Confidence score distribution
- Success rate by failure type
**Why it exists**: Business-specific metrics

---

## 📁 tests/ - Test Suite

### **tests/conftest.py**
**Purpose**: Pytest configuration and fixtures
**Contents**:
- Database fixtures (test DB)
- Mock clients (NVIDIA, GitHub, Slack)
- Test data factories
**Example**:
```python
import pytest
from sqlmodel import create_engine, Session

@pytest.fixture
def db_session():
    """Create test database session"""
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        yield session

@pytest.fixture
def mock_nvidia_client():
    """Mock NVIDIA API client"""
    client = Mock(spec=NVIDIAClient)
    client.classify.return_value = {
        "category": "imagepullbackoff",
        "root_cause": "Expired credentials",
        "fixability": "auto",
        "confidence": 0.92
    }
    return client

@pytest.fixture
def sample_incident():
    """Create sample incident for testing"""
    return Incident(
        incident_id="test_inc_123",
        timestamp=datetime.now(),
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        error_log="Error: ImagePullBackOff"
    )
```
**Why it exists**: Shared test fixtures and configuration

---

## 📁 tests/unit/ - Unit Tests

### **tests/unit/core/test_events.py**
**Purpose**: Test event models
**Contents**:
- Test event validation
- Test event factory
**Example**:
```python
def test_event_factory_github():
    headers = {"X-GitHub-Event": "workflow_run"}
    payload = {"action": "failed", "workflow": {...}}
    
    event = EventFactory.create(headers, payload)
    
    assert isinstance(event, GitHubWorkflowFailedEvent)
    assert event.source == IncidentSource.GITHUB
```
**Why it exists**: Ensure event parsing works correctly

### **tests/unit/core/test_models.py**
**Purpose**: Test domain models
**Contents**:
- Test incident model
- Test confidence score calculation
**Why it exists**: Ensure domain models work correctly

### **tests/unit/services/test_analyzer.py**
**Purpose**: Test analyzer service
**Contents**:
- Test LLM classification
- Test RAG retrieval
- Test confidence scoring
**Example**:
```python
async def test_analyzer_classifies_incident(
    mock_nvidia_client,
    mock_vector_repo,
    sample_incident
):
    analyzer = AnalyzerService(
        llm_client=mock_nvidia_client,
        embedder=mock_embedder,
        vector_repo=mock_vector_repo
    )
    
    result = await analyzer.analyze(sample_incident)
    
    assert result.category == "imagepullbackoff"
    assert result.confidence > 0.8
    assert len(result.similar_incidents) > 0
```
**Why it exists**: Test analyzer logic in isolation

### **tests/unit/services/test_decision.py**
**Purpose**: Test decision service
**Contents**: Test strategy pattern, business rules
**Why it exists**: Ensure decision logic is correct

### **tests/unit/services/test_confidence.py**
**Purpose**: Test confidence scoring
**Contents**: Test confidence calculation, calibration
**Why it exists**: Critical path - confidence determines auto-fix

### **tests/unit/domain/test_strategies.py**
**Purpose**: Test remediation strategies
**Contents**:
- Test SlackFirstStrategy
- Test ConservativeStrategy
**Why it exists**: Ensure strategies make correct decisions

### **tests/unit/domain/test_remediators.py**
**Purpose**: Test remediation actions
**Contents**:
- Test each remediation action
- Mock external API calls
**Example**:
```python
async def test_github_rerun_action(mock_github_client):
    action = GitHubRerunAction(github_client=mock_github_client)
    
    incident = create_test_incident(
        source=IncidentSource.GITHUB,
        context={"repository": "owner/repo", "run_id": 123}
    )
    
    result = await action.execute(incident)
    
    assert result.success
    mock_github_client.rerun_workflow.assert_called_once_with("owner/repo", 123)
```
**Why it exists**: Test remediation actions in isolation

### **tests/unit/domain/test_validators.py**
**Purpose**: Test validators
**Contents**:
- Test pre-remediation validation
- Test blast radius checks
**Why it exists**: Ensure safety checks work

### **tests/unit/utils/test_retry.py**
**Purpose**: Test retry logic
**Contents**: Test exponential backoff, max retries
**Why it exists**: Ensure retry utilities work

### **tests/unit/utils/test_lambda_utils.py**
**Purpose**: Test Lambda utilities
**Contents**: Test connection reuse, warm-up
**Why it exists**: Lambda-specific optimizations

---

## 📁 tests/integration/ - Integration Tests

### **tests/integration/test_api_webhook.py**
**Purpose**: Test webhook endpoint with real API
**Contents**:
- Send webhook payload
- Verify response
- Check database record created
**Example**:
```python
async def test_webhook_endpoint_creates_incident(client, db_session):
    payload = {
        "action": "failed",
        "workflow_run": {...}
    }
    
    response = await client.post(
        "/api/v1/webhook",
        json=payload,
        headers={"X-GitHub-Event": "workflow_run"}
    )
    
    assert response.status_code == 200
    
    # Verify incident created in database
    incident = db_session.query(IncidentTable).first()
    assert incident is not None
    assert incident.source == "github"
```
**Why it exists**: Test API endpoints with database

### **tests/integration/test_database.py**
**Purpose**: Test database operations
**Contents**:
- Test CRUD operations
- Test transactions
- Test migrations
**Why it exists**: Ensure database layer works

### **tests/integration/test_pgvector.py**
**Purpose**: Test pgvector operations
**Contents**:
- Test vector storage
- Test similarity search
- Test index performance
**Example**:
```python
def test_vector_similarity_search(db_session, vector_repo):
    # Store test embeddings
    incidents = [
        create_incident_with_embedding([0.1, 0.2, 0.3, ...]),
        create_incident_with_embedding([0.15, 0.25, 0.35, ...]),
        create_incident_with_embedding([0.9, 0.8, 0.7, ...])
    ]
    
    # Search for similar
    query_embedding = [0.12, 0.22, 0.32, ...]
    results = vector_repo.search(query_embedding, top_k=2)
    
    assert len(results) == 2
    assert results[0]["similarity"] > 0.9  # Very similar
```
**Why it exists**: Test vector search works correctly

### **tests/integration/test_nvidia_api.py**
**Purpose**: Test NVIDIA API integration
**Contents**:
- Test LLM calls (using VCR.py to record/replay)
- Test embedding calls
**Example**:
```python
import vcr

@vcr.use_cassette('fixtures/vcr_cassettes/nvidia_classify.yaml')
async def test_nvidia_classify(nvidia_client):
    prompt = "Analyze this error: ImagePullBackOff"
    result = await nvidia_client.classify(prompt)
    
    assert "category" in result
    assert "confidence" in result
```
**Why it exists**: Test API integration without hitting API every time

### **tests/integration/test_github_api.py**
**Purpose**: Test GitHub API integration
**Contents**: Test GitHub API calls (recorded with VCR.py)
**Why it exists**: Test GitHub integration

### **tests/integration/test_pipeline.py**
**Purpose**: Test full pipeline
**Contents**: Test event → analysis → decision → remediation flow
**Why it exists**: Integration test of main workflow

---

## 📁 tests/e2e/ - End-to-End Tests

### **tests/e2e/test_lambda_handler.py**
**Purpose**: Test Lambda handler end-to-end
**Contents**:
- Test with mock Lambda events
- Test API Gateway integration
**Example**:
```python
def test_lambda_handler_processes_webhook():
    event = {
        "httpMethod": "POST",
        "path": "/webhook",
        "headers": {"X-GitHub-Event": "workflow_run"},
        "body": json.dumps({...})
    }
    
    response = lambda_handler(event, {})
    
    assert response["statusCode"] == 200
```
**Why it exists**: Test Lambda handler works

### **tests/e2e/test_github_rerun.py**
**Purpose**: Test GitHub workflow rerun end-to-end
**Contents**:
- Receive webhook
- Analyze incident
- Rerun workflow
- Verify success
**Why it exists**: E2E test of common scenario

### **tests/e2e/test_argocd_sync.py**
**Purpose**: Test ArgoCD sync end-to-end
**Contents**: Full flow from webhook to ArgoCD sync
**Why it exists**: E2E test of ArgoCD integration

### **tests/e2e/test_full_flow.py**
**Purpose**: Test complete incident resolution flow
**Contents**:
- Webhook received
- Incident created
- Analyzed
- Fixed
- Verified
- Updated
**Why it exists**: Comprehensive E2E test

---

## 📁 tests/fixtures/ - Test Fixtures

### **tests/fixtures/events/*.json**
**Purpose**: Sample event payloads for testing
**Contents**: Real webhook payloads from GitHub, ArgoCD, K8s
**Why it exists**: Realistic test data

### **tests/fixtures/logs/*.txt**
**Purpose**: Sample error logs
**Contents**: Real error logs from various failure types
**Why it exists**: Test log parsing

### **tests/fixtures/responses/*.json**
**Purpose**: Sample API responses
**Contents**: Recorded API responses (NVIDIA, GitHub, Slack)
**Why it exists**: Mock API responses

---

## 📁 tests/performance/ - Performance Tests

### **tests/performance/test_cold_start.py**
**Purpose**: Measure Lambda cold start time
**Contents**:
- Time first invocation
- Compare with warm start
**Why it exists**: Optimize cold start performance

### **tests/performance/test_throughput.py**
**Purpose**: Test system throughput
**Contents**: Process multiple incidents concurrently
**Why it exists**: Ensure system can handle load

### **tests/performance/test_latency.py**
**Purpose**: Test latency of operations
**Contents**: Measure end-to-end latency
**Why it exists**: Ensure performance SLAs

---

## 📁 scripts/ - Operational Scripts

### **scripts/setup_pgvector.py**
**Purpose**: Initialize pgvector extension in PostgreSQL
**Contents**:
```python
from sqlalchemy import create_engine, text

def setup_pgvector(database_url: str):
    engine = create_engine(database_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        print("pgvector extension enabled")

if __name__ == "__main__":
    setup_pgvector(os.getenv("DATABASE_URL"))
```
**Why it exists**: One-time setup for pgvector

### **scripts/ingest_slack_history.py**
**Purpose**: Backfill Slack messages to vector database
**Contents**:
- Fetch Slack messages from channels
- Generate embeddings
- Store in vector DB
**Example**:
```python
async def ingest_slack_history(channels: List[str]):
    slack_client = SlackClient()
    embedder = EmbedderService()
    vector_repo = VectorRepository()
    
    for channel in channels:
        messages = await slack_client.get_channel_history(channel)
        
        for msg in messages:
            if "error" in msg.text.lower():
                embedding = await embedder.embed(msg.text)
                vector_repo.store_slack_message(msg, embedding)
        
        print(f"Ingested {len(messages)} messages from {channel}")
```
**Why it exists**: Initial data loading for RAG

### **scripts/reindex_vectors.py**
**Purpose**: Rebuild vector embeddings for all incidents
**Contents**:
- Fetch all incidents without embeddings
- Generate embeddings
- Update database
**Why it exists**: Regenerate embeddings after model change

### **scripts/generate_test_events.py**
**Purpose**: Generate synthetic test events
**Contents**: Create fake incidents for testing
**Why it exists**: Load testing, demo data

### **scripts/calibrate_confidence.py**
**Purpose**: Calibrate confidence thresholds
**Contents**:
- Analyze historical incidents
- Calculate actual success rates
- Recommend new thresholds
**Example**:
```python
def calibrate_confidence():
    incidents = get_all_resolved_incidents()
    
    # Group by confidence bucket
    buckets = defaultdict(list)
    for inc in incidents:
        bucket = int(inc.confidence * 10) / 10  # Round to 0.1
        buckets[bucket].append(inc)
    
    # Calculate success rate per bucket
    for confidence, incidents_in_bucket in sorted(buckets.items()):
        success_rate = sum(1 for i in incidents_in_bucket if i.outcome == "success") / len(incidents_in_bucket)
        print(f"Confidence {confidence}: {success_rate:.2%} success rate ({len(incidents_in_bucket)} incidents)")
    
    # Recommend threshold for 95% success rate
    for confidence in reversed(sorted(buckets.keys())):
        if success_rate >= 0.95:
            print(f"\nRecommended threshold: {confidence}")
            break
```
**Why it exists**: Data-driven confidence tuning

### **scripts/export_incidents.py**
**Purpose**: Export incidents to CSV/JSON
**Contents**: Query database and export
**Why it exists**: Data analysis, reporting

### **scripts/seed_database.py**
**Purpose**: Seed database with sample data
**Contents**: Create test incidents, feedback, etc.
**Why it exists**: Demo environment, development

### **scripts/health_check.py**
**Purpose**: Standalone health check script
**Contents**:
- Check database connectivity
- Check NVIDIA API
- Check external services
**Why it exists**: Monitoring, troubleshooting

### **scripts/deploy_lambda.sh**
**Purpose**: Deploy Lambda function
**Contents**:
```bash
#!/bin/bash
set -e

ENV=${1:-dev}

echo "Building Docker image..."
docker build -f Dockerfile.lambda -t codehealer:$ENV .

echo "Tagging for ECR..."
docker tag codehealer:$ENV $ECR_REPO:$ENV

echo "Pushing to ECR..."
docker push $ECR_REPO:$ENV

echo "Updating Lambda function..."
aws lambda update-function-code \
    --function-name codehealer-$ENV \
    --image-uri $ECR_REPO:$ENV

echo "Deployment complete!"
```
**Why it exists**: Automated deployment

### **scripts/benchmark_lambda.py**
**Purpose**: Benchmark Lambda performance
**Contents**: Invoke Lambda multiple times, measure latency
**Why it exists**: Performance testing

---

## 📁 config/ - Configuration Files

### **config/dev.yaml**
**Purpose**: Development environment configuration
**Contents**:
```yaml
environment: dev
log_level: DEBUG
confidence_threshold: 0.75
max_fixes_per_hour: 100
requires_approval: false
```
**Why it exists**: Dev-specific settings

### **config/staging.yaml**
**Purpose**: Staging environment configuration
**Contents**: Similar to prod but with lower thresholds
**Why it exists**: Pre-prod testing

### **config/prod.yaml**
**Purpose**: Production environment configuration
**Contents**:
```yaml
environment: prod
log_level: INFO
confidence_threshold: 0.95
max_fixes_per_hour: 10
requires_approval: true
```
**Why it exists**: Production settings

### **config/logging.yaml**
**Purpose**: Logging configuration
**Contents**: Log levels, formats, outputs
**Why it exists**: Centralized logging config

---

## 📁 infrastructure/terraform/ - Infrastructure as Code

### **infrastructure/terraform/main.tf**
**Purpose**: Main Terraform configuration
**Contents**:
- Import all modules
- Set up providers (AWS)
**Example**:
```hcl
terraform {
  required_version = ">= 1.0"
  
  backend "s3" {
    bucket = "codehealer-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

module "vpc" {
  source = "./modules/vpc"
  environment = var.environment
}

module "rds" {
  source = "./modules/rds"
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
}

module "lambda" {
  source = "./modules/lambda"
  environment = var.environment
  database_url = module.rds.connection_string
}
```
**Why it exists**: Define all infrastructure

### **infrastructure/terraform/variables.tf**
**Purpose**: Input variables
**Contents**:
```hcl
variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}
```
**Why it exists**: Parameterize infrastructure

### **infrastructure/terraform/outputs.tf**
**Purpose**: Output values
**Contents**:
```hcl
output "api_gateway_url" {
  description = "API Gateway endpoint URL"
  value       = module.api_gateway.url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.lambda.function_name
}
```
**Why it exists**: Export important values

### **infrastructure/terraform/versions.tf**
**Purpose**: Terraform version constraints
**Contents**: Required Terraform and provider versions
**Why it exists**: Ensure compatible versions

### **infrastructure/terraform/terraform.tfvars.example**
**Purpose**: Example variable values
**Contents**:
```hcl
environment = "dev"
aws_region  = "us-east-1"
lambda_memory = 1024
```
**Why it exists**: Template for actual tfvars file

### **infrastructure/terraform/modules/vpc/main.tf**
**Purpose**: VPC module
**Contents**:
- Create VPC
- Create subnets (public + private)
- Create NAT gateway
- Create route tables
**Why it exists**: Network infrastructure

### **infrastructure/terraform/modules/rds/main.tf**
**Purpose**: RDS module
**Contents**:
```hcl
resource "aws_db_instance" "codehealer" {
  identifier           = "codehealer-${var.environment}"
  engine               = "postgres"
  engine_version       = "15.3"
  instance_class       = "db.t3.micro"
  allocated_storage    = 20
  storage_type         = "gp3"
  
  username             = "codehealer"
  password             = data.aws_secretsmanager_secret_version.db_password.secret_string
  
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
  
  backup_retention_period = 7
  skip_final_snapshot    = var.environment != "prod"
  
  parameter_group_name = aws_db_parameter_group.pgvector.name
  
  tags = {
    Environment = var.environment
  }
}
```
**Why it exists**: PostgreSQL database

### **infrastructure/terraform/modules/rds/parameter_group.tf**
**Purpose**: RDS parameter group for pgvector
**Contents**:
```hcl
resource "aws_db_parameter_group" "pgvector" {
  name   = "codehealer-pgvector-${var.environment}"
  family = "postgres15"
  
  parameter {
    name  = "shared_preload_libraries"
    value = "vector"
  }
  
  tags = {
    Environment = var.environment
  }
}
```
**Why it exists**: Enable pgvector extension

### **infrastructure/terraform/modules/lambda/main.tf**
**Purpose**: Lambda function module
**Contents**:
```hcl
resource "aws_lambda_function" "codehealer" {
  function_name = "codehealer-${var.environment}"
  role          = aws_iam_role.lambda.arn
  
  package_type = "Image"
  image_uri    = "${var.ecr_repository_url}:${var.environment}"
  
  memory_size = var.lambda_memory
  timeout     = 60
  
  environment {
    variables = {
      ENVIRONMENT   = var.environment
      DATABASE_URL  = var.database_url
      NVIDIA_API_KEY = data.aws_secretsmanager_secret_version.nvidia_key.secret_string
      GITHUB_TOKEN  = data.aws_secretsmanager_secret_version.github_token.secret_string
    }
  }
  
  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }
  
  tags = {
    Environment = var.environment
  }
}

resource "aws_lambda_function_url" "codehealer" {
  function_name      = aws_lambda_function.codehealer.function_name
  authorization_type = "NONE"
}
```
**Why it exists**: Lambda function definition

### **infrastructure/terraform/modules/lambda/iam.tf**
**Purpose**: Lambda IAM role and policies
**Contents**:
```hcl
resource "aws_iam_role" "lambda" {
  name = "codehealer-lambda-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "secrets_access" {
  name = "secrets-access"
  role = aws_iam_role.lambda.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = [
        data.aws_secretsmanager_secret.nvidia_key.arn,
        data.aws_secretsmanager_secret.github_token.arn
      ]
    }]
  })
}
```
**Why it exists**: Lambda permissions

### **infrastructure/terraform/modules/api_gateway/main.tf**
**Purpose**: API Gateway module
**Contents**: Create REST API, integrate with Lambda
**Why it exists**: HTTP endpoint for Lambda

### **infrastructure/terraform/modules/sqs/main.tf**
**Purpose**: SQS queue module (optional)
**Contents**: Create queue for async processing
**Why it exists**: Async task processing

### **infrastructure/terraform/modules/secrets/main.tf**
**Purpose**: Secrets Manager module
**Contents**: Store secrets (API keys, tokens)
**Why it exists**: Secure secret storage

### **infrastructure/terraform/modules/cloudwatch/main.tf**
**Purpose**: CloudWatch module
**Contents**:
- Log groups
- Alarms (Lambda errors, duration)
- Dashboards
**Why it exists**: Monitoring and alerting

### **infrastructure/terraform/modules/ecr/main.tf**
**Purpose**: ECR repository module
**Contents**:
```hcl
resource "aws_ecr_repository" "codehealer" {
  name = "codehealer"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  image_tag_mutability = "MUTABLE"
}
```
**Why it exists**: Docker image storage

### **infrastructure/terraform/modules/iam/main.tf**
**Purpose**: Shared IAM resources
**Contents**: Common IAM roles and policies
**Why it exists**: Centralized IAM management

### **infrastructure/terraform/environments/dev/main.tf**
**Purpose**: Dev environment configuration
**Contents**:
```hcl
module "infrastructure" {
  source = "../../"
  
  environment   = "dev"
  lambda_memory = 512
  rds_instance  = "db.t3.micro"
}
```
**Why it exists**: Dev-specific infrastructure

---

## 📁 infrastructure/helm/ - Kubernetes Helm Charts

### **infrastructure/helm/codehealer/Chart.yaml**
**Purpose**: Helm chart metadata
**Contents**:
```yaml
apiVersion: v2
name: codehealer
description: Autonomous incident remediation system
version: 0.1.0
appVersion: "0.1.0"
```
**Why it exists**: Helm chart definition

### **infrastructure/helm/codehealer/values.yaml**
**Purpose**: Default values for Helm chart
**Contents**:
```yaml
replicaCount: 2

image:
  repository: codehealer
  tag: latest
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: codehealer.example.com
      paths:
        - path: /
          pathType: Prefix

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
```
**Why it exists**: Configurable Helm values

### **infrastructure/helm/codehealer/templates/deployment.yaml**
**Purpose**: Kubernetes deployment template
**Contents**: Pod spec, env vars, volumes
**Why it exists**: Define how pods run

### **infrastructure/helm/codehealer/templates/service.yaml**
**Purpose**: Kubernetes service template
**Contents**: Service definition
**Why it exists**: Expose pods

### **infrastructure/helm/codehealer/templates/ingress.yaml**
**Purpose**: Kubernetes ingress template
**Contents**: Ingress rules
**Why it exists**: External access

---

## 📁 .github/workflows/ - GitHub Actions

### **.github/workflows/ci.yml**
**Purpose**: Continuous Integration workflow
**Contents**:
```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install dependencies
        run: uv sync
      
      - name: Run tests
        run: uv run pytest --cov=app --cov-report=xml
      
      - name: Lint
        run: |
          uv run ruff check .
          uv run mypy app/
```
**Why it exists**: Automated testing

### **.github/workflows/deploy-lambda-dev.yml**
**Purpose**: Deploy to dev environment
**Contents**:
- Build Docker image
- Push to ECR
- Update Lambda function
**Why it exists**: Automated deployment

### **.github/workflows/docker-build.yml**
**Purpose**: Build and push Docker images
**Contents**: Build image, scan for vulnerabilities, push to ECR
**Why it exists**: Container image building

---

## 📁 docs/ - Documentation

### **docs/index.md**
**Purpose**: Documentation home page
**Contents**: Overview, links to other docs
**Why it exists**: Documentation entry point

### **docs/architecture/overview.md**
**Purpose**: High-level architecture overview
**Contents**:
- System diagram
- Component descriptions
- Data flow
**Why it exists**: Understand the system

### **docs/architecture/lambda-design.md**
**Purpose**: Lambda-specific architecture
**Contents**:
- Why Lambda
- Cold start optimization
- Connection pooling
**Why it exists**: Explain Lambda design decisions

### **docs/architecture/decision-records/007-lambda-over-ecs.md**
**Purpose**: Architecture Decision Record (ADR)
**Contents**:
```markdown
# ADR 007: Lambda over ECS

## Status
Accepted

## Context
Need to choose deployment platform: Lambda vs ECS

## Decision
Use AWS Lambda with Docker containers

## Consequences
Pros:
- Lower cost ($0.20/mo vs $50/mo)
- Zero ops
- Auto-scaling

Cons:
- Cold starts (2-5s)
- 15min timeout
- Connection pooling challenges

## Alternatives Considered
- ECS Fargate
- EC2
```
**Why it exists**: Document key decisions

### **docs/deployment/lambda-deployment.md**
**Purpose**: Lambda deployment guide
**Contents**: Step-by-step deployment instructions
**Why it exists**: Deployment documentation

### **docs/api/openapi.yaml**
**Purpose**: OpenAPI specification
**Contents**: Auto-generated from FastAPI
**Why it exists**: API documentation

### **docs/development/setup.md**
**Purpose**: Development setup guide
**Contents**:
```markdown
# Development Setup

## Prerequisites
- Python 3.11+
- uv package manager
- Docker
- PostgreSQL

## Setup Steps
1. Clone repository
2. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. Install dependencies: `uv sync`
4. Start services: `docker-compose up`
5. Run migrations: `uv run alembic upgrade head`
6. Run app: `uv run uvicorn app.main:app --reload`
```
**Why it exists**: Help developers get started

### **docs/operations/runbooks/lambda-timeout.md**
**Purpose**: Runbook for Lambda timeouts
**Contents**:
- Symptoms
- Diagnosis steps
- Resolution steps
**Why it exists**: Operational procedures

---

## 📁 monitoring/ - Monitoring Configuration

### **monitoring/cloudwatch/dashboards/lambda-performance.json**
**Purpose**: CloudWatch dashboard definition
**Contents**: Widgets for Lambda metrics
**Why it exists**: Visual monitoring

### **monitoring/cloudwatch/alarms/lambda-errors.json**
**Purpose**: CloudWatch alarm definition
**Contents**: Alert when Lambda error rate > 5%
**Why it exists**: Alerting

---

**This completes the comprehensive documentation of all files in the CodeHealer project!**

Each file has a clear purpose and fits into the overall architecture. The structure follows clean architecture principles with clear separation of concerns.
