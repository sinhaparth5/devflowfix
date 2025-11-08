# CodeHealer - Complete File Documentation (Part 2)
## Continued: Adapters, Domain, Utils, Tests, Infrastructure

---

## 📁 app/adapters/ - Adapters (Hexagonal Architecture)

**Purpose**: All external integrations isolated here. Business logic (core/services/domain) never talks directly to external systems - always goes through adapters.

---

## 📁 app/adapters/ai/ - AI/ML Adapters

### **app/adapters/ai/base.py**
**Purpose**: Abstract base class for AI adapters
**Contents**:
- `BaseAIAdapter` interface
- Methods: `classify()`, `embed()`, `complete()`
**Why it exists**: Allows swapping AI providers (NVIDIA → OpenAI → Anthropic)

### **app/adapters/ai/nvidia/client.py**
**Purpose**: HTTP client for NVIDIA API
**Contents**:
- HTTP client using httpx
- Authentication with NGC API key
- Rate limiting and retries
- Error handling
**Example**:
```python
class NVIDIAClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    async def post(self, endpoint: str, payload: dict) -> dict:
        response = await self.client.post(
            f"{self.base_url}/{endpoint}",
            json=payload
        )
        response.raise_for_status()
        return response.json()
```
**Why it exists**: Reusable HTTP client for all NVIDIA API calls

### **app/adapters/ai/nvidia/llm.py**
**Purpose**: LLM inference via NVIDIA API
**Contents**:
- Wrapper for text generation API
- Handles prompt formatting
- Parses LLM responses
**Example**:
```python
class NVIDIALLMClient:
    async def classify(self, prompt: str) -> dict:
        response = await self.client.post("/v1/chat/completions", {
            "model": "meta/llama-3.1-8b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 512
        })
        
        # Parse structured output from LLM
        return self._parse_classification(response["choices"][0]["message"]["content"])
```
**Why it exists**: LLM-specific logic separated from HTTP client

### **app/adapters/ai/nvidia/embeddings.py**
**Purpose**: Generate embeddings via NVIDIA API
**Contents**:
- Call embedding endpoint
- Handle batching for multiple texts
- Normalize embeddings
**Example**:
```python
class NVIDIAEmbeddingClient:
    async def embed(self, text: str) -> List[float]:
        response = await self.client.post("/v1/embeddings", {
            "model": "NV-Embed-QA",
            "input": text
        })
        return response["data"][0]["embedding"]
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Batch processing for efficiency
        pass
```
**Why it exists**: Embedding-specific API wrapper

### **app/adapters/ai/nvidia/prompts.py**
**Purpose**: Prompt templates for LLM
**Contents**:
- Classification prompt template
- Few-shot examples
- System prompts
**Example**:
```python
CLASSIFICATION_PROMPT = """
[INST] You are an expert DevOps engineer. Analyze this deployment failure and classify it.

Error Log:
{error_log}

Context:
- Repository: {repo}
- Branch: {branch}
- Commit: {commit}

Similar past incidents:
{similar_incidents}

Respond in JSON format:
{{
    "category": "imagepullbackoff" | "oomkilled" | "crashloop" | "buildfailure",
    "root_cause": "brief explanation",
    "fixability": "auto" | "manual",
    "confidence": 0.0 to 1.0
}}
[/INST]
"""

def build_classification_prompt(event: NormalizedEvent, similar: List[dict]) -> str:
    return CLASSIFICATION_PROMPT.format(
        error_log=event.error_log,
        repo=event.context.get("repository"),
        branch=event.context.get("branch"),
        commit=event.context.get("commit"),
        similar_incidents=format_similar_incidents(similar)
    )
```
**Why it exists**: Centralized prompt management, easier to iterate

### **app/adapters/ai/nvidia/cache.py**
**Purpose**: Cache LLM/embedding responses
**Contents**:
- Cache responses to avoid redundant API calls
- TTL-based expiration
- Cache key generation
**Example**:
```python
class ResponseCache:
    def __init__(self, cache_adapter: CacheAdapter):
        self.cache = cache_adapter
    
    def get_cached_response(self, prompt: str) -> Optional[dict]:
        cache_key = f"llm:{hash(prompt)}"
        return self.cache.get(cache_key)
    
    def cache_response(self, prompt: str, response: dict, ttl: int = 3600):
        cache_key = f"llm:{hash(prompt)}"
        self.cache.set(cache_key, response, ttl=ttl)
```
**Why it exists**: Reduce API costs and latency for duplicate queries

### **app/adapters/ai/nvidia/config.py**
**Purpose**: NVIDIA API configuration
**Contents**:
- Model names
- API endpoints
- Default parameters
**Example**:
```python
NVIDIA_CONFIG = {
    "llm_model": "meta/llama-3.1-8b-instruct",
    "embedding_model": "NV-Embed-QA",
    "base_url": "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions",
    "max_tokens": 512,
    "temperature": 0.2
}
```
**Why it exists**: Centralized NVIDIA-specific configuration

### **app/adapters/ai/fallback.py**
**Purpose**: Fallback to other AI providers
**Contents**:
- OpenAI client
- Anthropic client
- Automatic fallback on NVIDIA API failure
**Example**:
```python
class FallbackAIClient:
    def __init__(self, primary: NVIDIAClient, fallback: OpenAIClient):
        self.primary = primary
        self.fallback = fallback
    
    async def classify(self, prompt: str) -> dict:
        try:
            return await self.primary.classify(prompt)
        except Exception as e:
            logger.warning(f"Primary AI failed, using fallback: {e}")
            return await self.fallback.classify(prompt)
```
**Why it exists**: Resilience - don't fail if NVIDIA API is down

---

## 📁 app/adapters/database/postgres/ - PostgreSQL with pgvector

### **app/adapters/database/base.py**
**Purpose**: Abstract repository interface
**Contents**:
- `BaseRepository` abstract class
- CRUD methods: create, read, update, delete
**Example**:
```python
from abc import ABC, abstractmethod

class BaseRepository(ABC):
    @abstractmethod
    def create(self, entity): pass
    
    @abstractmethod
    def get_by_id(self, id: str): pass
    
    @abstractmethod
    def update(self, entity): pass
    
    @abstractmethod
    def delete(self, id: str): pass
```
**Why it exists**: Common interface for all repositories

### **app/adapters/database/postgres/connection.py**
**Purpose**: Database connection pool management
**Contents**:
- Create SQLAlchemy engine
- Connection pool configuration
- Lambda-optimized settings (small pool size)
**Example**:
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

def create_db_engine(database_url: str, is_lambda: bool = True):
    if is_lambda:
        # Lambda needs NullPool (no persistent connections)
        return create_engine(
            database_url,
            poolclass=NullPool,
            echo=False
        )
    else:
        # Normal connection pooling for local dev
        return create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            echo=False
        )
```
**Why it exists**: Lambda requires special connection handling

### **app/adapters/database/postgres/models.py**
**Purpose**: SQLModel table definitions (ORM models)
**Contents**:
- Database table schemas using SQLModel
- Relationships between tables
**Example**:
```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
from pgvector.sqlalchemy import Vector

class IncidentTable(SQLModel, table=True):
    __tablename__ = "incidents"
    
    incident_id: str = Field(primary_key=True)
    timestamp: datetime
    source: str
    severity: str
    error_log: str
    root_cause: Optional[str] = None
    confidence: Optional[float] = None
    outcome: Optional[str] = None
    resolution_time_seconds: Optional[int] = None
    embedding: Optional[Vector] = Field(sa_column=Vector(768))  # pgvector
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class FeedbackTable(SQLModel, table=True):
    __tablename__ = "feedback"
    
    feedback_id: str = Field(primary_key=True)
    incident_id: str = Field(foreign_key="incidents.incident_id")
    helpful: bool
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```
**Why it exists**: ORM models for database tables

### **app/adapters/database/postgres/extensions.py**
**Purpose**: pgvector extension setup and utilities
**Contents**:
- Enable pgvector extension
- Helper functions for vector operations
- Distance calculation functions
**Example**:
```python
from sqlalchemy import text

def enable_pgvector(engine):
    """Enable pgvector extension in PostgreSQL"""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    # Use PostgreSQL's built-in cosine distance: 1 - cosine_distance
    pass

def create_ivfflat_index(engine, table_name: str, column_name: str):
    """Create IVFFlat index for fast approximate search"""
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS {table_name}_{column_name}_idx
            ON {table_name}
            USING ivfflat ({column_name} vector_cosine_ops)
            WITH (lists = 100);
        """))
```
**Why it exists**: pgvector setup and utility functions

### **app/adapters/database/postgres/repositories/incident.py**
**Purpose**: Incident repository (CRUD operations)
**Contents**:
- Create, read, update, delete incidents
- Query incidents with filters
- Aggregate statistics
**Example**:
```python
class IncidentRepository(BaseRepository):
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, event: NormalizedEvent) -> Incident:
        db_incident = IncidentTable(
            incident_id=event.incident_id,
            timestamp=event.timestamp,
            source=event.source,
            severity=event.severity,
            error_log=event.error_log
        )
        self.session.add(db_incident)
        self.session.commit()
        return self._to_domain(db_incident)
    
    def get_by_id(self, incident_id: str) -> Optional[Incident]:
        db_incident = self.session.get(IncidentTable, incident_id)
        return self._to_domain(db_incident) if db_incident else None
    
    def list_incidents(
        self,
        skip: int = 0,
        limit: int = 100,
        source: Optional[str] = None
    ) -> List[Incident]:
        query = self.session.query(IncidentTable)
        if source:
            query = query.filter(IncidentTable.source == source)
        db_incidents = query.offset(skip).limit(limit).all()
        return [self._to_domain(i) for i in db_incidents]
    
    def _to_domain(self, db_incident: IncidentTable) -> Incident:
        # Convert ORM model to domain model
        pass
```
**Why it exists**: Repository pattern - isolates database logic

### **app/adapters/database/postgres/repositories/feedback.py**
**Purpose**: Feedback repository
**Contents**:
- Store human feedback
- Query feedback for analysis
**Why it exists**: Separate repository for feedback data

### **app/adapters/database/postgres/repositories/analytics.py**
**Purpose**: Analytics queries repository
**Contents**:
- Complex aggregation queries
- Success rate calculations
- Time-series data
**Example**:
```python
class AnalyticsRepository:
    def get_success_rate(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> float:
        result = self.session.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE outcome = 'success') * 1.0 / COUNT(*) as rate
            FROM incidents
            WHERE timestamp BETWEEN :start AND :end
        """), {"start": start_date, "end": end_date})
        return result.scalar()
```
**Why it exists**: Complex analytics queries separated from basic CRUD

### **app/adapters/database/postgres/repositories/vector.py**
**Purpose**: Vector search operations with pgvector
**Contents**:
- Store embeddings
- Vector similarity search
- Hybrid search (vector + metadata filters)
**Example**:
```python
class VectorRepository:
    def store_embedding(self, incident_id: str, embedding: List[float]):
        """Store embedding for incident"""
        self.session.execute(
            text("UPDATE incidents SET embedding = :emb WHERE incident_id = :id"),
            {"emb": embedding, "id": incident_id}
        )
        self.session.commit()
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[dict] = None
    ) -> List[dict]:
        """Vector similarity search using pgvector"""
        # Use cosine distance with pgvector
        query = text("""
            SELECT 
                incident_id,
                source,
                error_log,
                root_cause,
                confidence,
                outcome,
                1 - (embedding <=> :query_vec) as similarity
            FROM incidents
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :query_vec
            LIMIT :limit
        """)
        
        results = self.session.execute(
            query,
            {"query_vec": query_embedding, "limit": top_k}
        ).fetchall()
        
        return [dict(row) for row in results]
    
    def hybrid_search(
        self,
        query_embedding: List[float],
        source: str,
        min_confidence: float,
        top_k: int = 5
    ) -> List[dict]:
        """Hybrid search: vector similarity + metadata filters"""
        query = text("""
            SELECT *,
                1 - (embedding <=> :query_vec) as similarity
            FROM incidents
            WHERE 
                embedding IS NOT NULL
                AND source = :source
                AND confidence >= :min_conf
            ORDER BY embedding <=> :query_vec
            LIMIT :limit
        """)
        
        results = self.session.execute(query, {
            "query_vec": query_embedding,
            "source": source,
            "min_conf": min_confidence,
            "limit": top_k
        }).fetchall()
        
        return [dict(row) for row in results]
```
**Why it exists**: pgvector-specific search operations

### **app/adapters/database/postgres/queries.py**
**Purpose**: Complex SQL queries
**Contents**:
- Reusable SQL query templates
- Parameterized queries
**Why it exists**: Keep complex SQL out of repositories

### **app/adapters/database/postgres/migrations/env.py**
**Purpose**: Alembic migration environment setup
**Contents**: Alembic configuration for running migrations
**Why it exists**: Required by Alembic for migrations

### **app/adapters/database/postgres/migrations/script.py.mako**
**Purpose**: Template for generating new migration files
**Contents**: Mako template used by Alembic
**Why it exists**: Standardizes migration file format

### **app/adapters/database/postgres/migrations/versions/001_initial.py**
**Purpose**: Initial database schema migration
**Contents**:
```python
def upgrade():
    op.create_table(
        'incidents',
        sa.Column('incident_id', sa.String(), primary_key=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        # ... all columns
    )
    op.create_index('idx_incidents_timestamp', 'incidents', ['timestamp'])
```
**Why it exists**: Creates initial database schema

### **app/adapters/database/postgres/migrations/versions/002_enable_pgvector.py**
**Purpose**: Enable pgvector extension
**Contents**:
```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```
**Why it exists**: Enables pgvector in PostgreSQL

### **app/adapters/database/postgres/migrations/versions/003_add_vector_indexes.py**
**Purpose**: Add vector indexes for fast search
**Contents**:
```python
def upgrade():
    op.execute("""
        CREATE INDEX incidents_embedding_idx 
        ON incidents 
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)
```
**Why it exists**: Speeds up vector similarity search

---

## 📁 app/adapters/external/ - External API Adapters

### **app/adapters/external/base.py**
**Purpose**: Base class for external API clients
**Contents**:
- Common HTTP client logic
- Retry logic
- Error handling
**Why it exists**: DRY - shared logic for all external APIs

### **app/adapters/external/github/client.py**
**Purpose**: GitHub API client
**Contents**:
- HTTP client for GitHub REST API
- Authentication with GitHub token/App
- Rate limiting handling
**Example**:
```python
class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.github.com"
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
        )
```
**Why it exists**: Centralized GitHub API access

### **app/adapters/external/github/actions.py**
**Purpose**: GitHub Actions operations
**Contents**:
- Rerun workflow
- Cancel workflow
- Get workflow logs
**Example**:
```python
class GitHubActionsAdapter:
    async def rerun_workflow(self, repo: str, run_id: int):
        """Rerun a failed workflow"""
        await self.client.post(
            f"/repos/{repo}/actions/runs/{run_id}/rerun"
        )
    
    async def get_workflow_logs(self, repo: str, run_id: int) -> str:
        """Download workflow logs"""
        response = await self.client.get(
            f"/repos/{repo}/actions/runs/{run_id}/logs"
        )
        return response.text
```
**Why it exists**: GitHub Actions-specific operations

### **app/adapters/external/github/webhooks.py**
**Purpose**: GitHub webhook verification
**Contents**:
- Verify webhook HMAC signature
- Parse webhook payloads
**Example**:
```python
import hmac
import hashlib

class GitHubWebhookVerifier:
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """Verify GitHub webhook signature"""
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
```
**Why it exists**: Security - verify webhooks are from GitHub

### **app/adapters/external/github/auth.py**
**Purpose**: GitHub App authentication
**Contents**:
- Generate JWT for GitHub App
- Get installation access token
**Why it exists**: GitHub App auth is complex (JWT → access token)

### **app/adapters/external/argocd/client.py**
**Purpose**: ArgoCD API client
**Contents**: HTTP client for ArgoCD REST API
**Why it exists**: ArgoCD API access

### **app/adapters/external/argocd/sync.py**
**Purpose**: ArgoCD sync operations
**Contents**:
- Trigger application sync
- Get sync status
**Example**:
```python
class ArgoCDSyncAdapter:
    async def sync_application(self, app_name: str):
        """Trigger ArgoCD application sync"""
        await self.client.post(
            f"/api/v1/applications/{app_name}/sync"
        )
```
**Why it exists**: ArgoCD sync operations

### **app/adapters/external/argocd/rollback.py**
**Purpose**: ArgoCD rollback operations
**Contents**:
- Rollback to previous revision
- Get revision history
**Why it exists**: Rollback specific to ArgoCD

### **app/adapters/external/kubernetes/client.py**
**Purpose**: Kubernetes API client
**Contents**: kubernetes-python client wrapper
**Why it exists**: K8s API access

### **app/adapters/external/kubernetes/pods.py**
**Purpose**: Pod operations
**Contents**:
- Restart pod (delete pod)
- Get pod logs
- Get pod status
**Example**:
```python
class K8sPodsAdapter:
    async def restart_pod(self, namespace: str, pod_name: str):
        """Restart pod by deleting it (deployment will recreate)"""
        await self.client.delete_namespaced_pod(pod_name, namespace)
    
    async def get_pod_logs(self, namespace: str, pod_name: str) -> str:
        """Get pod logs"""
        return await self.client.read_namespaced_pod_log(pod_name, namespace)
```
**Why it exists**: Pod-specific operations

### **app/adapters/external/kubernetes/deployments.py**
**Purpose**: Deployment operations
**Contents**:
- Scale deployment
- Update image
- Rollback deployment
**Why it exists**: Deployment operations

### **app/adapters/external/kubernetes/secrets.py**
**Purpose**: Secret management
**Contents**:
- Update secrets (for credential rotation)
- Get secrets
**Why it exists**: Secret operations

### **app/adapters/external/kubernetes/events.py**
**Purpose**: Watch Kubernetes events
**Contents**:
- Stream events (for real-time monitoring - future)
**Why it exists**: K8s event watching

### **app/adapters/external/slack/client.py**
**Purpose**: Slack API client
**Contents**: HTTP client for Slack Web API
**Why it exists**: Slack API access

### **app/adapters/external/slack/search.py**
**Purpose**: Search Slack messages
**Contents**:
- Search messages by keyword
- Search in specific channels
**Example**:
```python
class SlackSearchAdapter:
    async def search_messages(self, query: str) -> List[dict]:
        """Search Slack messages"""
        response = await self.client.post(
            "https://slack.com/api/search.messages",
            json={"query": query}
        )
        return response["messages"]["matches"]
```
**Why it exists**: RAG retrieval from Slack

### **app/adapters/external/slack/notifications.py**
**Purpose**: Send Slack notifications
**Contents**:
- Post message to channel
- Send DM
- Rich formatting (blocks)
**Example**:
```python
class SlackNotifier:
    async def notify_incident(self, incident: Incident):
        """Notify Slack channel about new incident"""
        await self.client.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel": "#incidents",
                "text": f"New incident: {incident.incident_id}",
                "blocks": [...]  # Rich formatting
            }
        )
```
**Why it exists**: Send notifications to Slack

### **app/adapters/external/slack/approvals.py**
**Purpose**: Slack approval workflow with interactive messages
**Contents**:
- Send approval request with buttons
- Handle button clicks (interactive message callbacks)
**Example**:
```python
class SlackApprovalAdapter:
    async def request_approval(
        self,
        incident: Incident,
        remediation_plan: RemediationPlan
    ):
        """Send approval request to Slack"""
        await self.client.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel": "#approvals",
                "text": f"Approve fix for {incident.incident_id}?",
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*Incident*: {incident.root_cause}"}},
                    {"type": "actions", "elements": [
                        {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "value": "approve"},
                        {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "value": "reject"}
                    ]}
                ]
            }
        )
```
**Why it exists**: Human-in-the-loop approval

### **app/adapters/external/slack/bot.py**
**Purpose**: Slack bot event handling
**Contents**:
- Handle Slack events (app mentions, button clicks)
- Socket mode or HTTP mode
**Why it exists**: Respond to Slack events

### **app/adapters/external/pagerduty/client.py**
**Purpose**: PagerDuty API client
**Contents**: HTTP client for PagerDuty
**Why it exists**: PagerDuty integration

### **app/adapters/external/pagerduty/incidents.py**
**Purpose**: PagerDuty incident management
**Contents**:
- Create incident
- Update incident
- Resolve incident
**Why it exists**: Escalate to PagerDuty for critical issues

---

## 📁 app/adapters/queue/ - Message Queue Adapters

### **app/adapters/queue/base.py**
**Purpose**: Abstract queue interface
**Contents**: `BaseQueueAdapter` with enqueue/dequeue methods
**Why it exists**: Pluggable queue implementations

### **app/adapters/queue/sqs.py**
**Purpose**: AWS SQS adapter
**Contents**:
- Send message to SQS
- Receive message from SQS
- Delete message after processing
**Example**:
```python
class SQSAdapter(BaseQueueAdapter):
    async def enqueue(self, message: dict, queue_name: str):
        """Send message to SQS queue"""
        await self.sqs_client.send_message(
            QueueUrl=queue_name,
            MessageBody=json.dumps(message)
        )
```
**Why it exists**: Async processing of long-running tasks

### **app/adapters/queue/local.py**
**Purpose**: In-memory queue for development
**Contents**: Simple Python queue
**Why it exists**: Local testing without SQS

---

## 📁 app/adapters/cache/ - Caching Adapters

### **app/adapters/cache/base.py**
**Purpose**: Abstract cache interface
**Contents**: `BaseCacheAdapter` with get/set/delete methods
**Why it exists**: Pluggable cache implementations

### **app/adapters/cache/redis.py**
**Purpose**: Redis cache adapter
**Contents**: Redis client wrapper
**Why it exists**: Production caching with Redis

### **app/adapters/cache/memory.py**
**Purpose**: In-memory cache
**Contents**: Simple Python dict with TTL
**Example**:
```python
class MemoryCache(BaseCacheAdapter):
    def __init__(self):
        self.cache = {}
    
    def get(self, key: str) -> Optional[Any]:
        entry = self.cache.get(key)
        if entry and entry["expires_at"] > time.time():
            return entry["value"]
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        self.cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl
        }
```
**Why it exists**: Lambda-friendly caching (no external dependency)

---

## 📁 app/adapters/secrets/ - Secrets Management

### **app/adapters/secrets/base.py**
**Purpose**: Abstract secrets interface
**Contents**: `BaseSecretsAdapter` with get_secret method
**Why it exists**: Pluggable secrets backends

### **app/adapters/secrets/aws.py**
**Purpose**: AWS Secrets Manager adapter
**Contents**: Fetch secrets from AWS Secrets Manager
**Example**:
```python
class AWSSecretsAdapter:
    async def get_secret(self, secret_name: str) -> str:
        """Fetch secret from AWS Secrets Manager"""
        response = await self.client.get_secret_value(SecretId=secret_name)
        return response["SecretString"]
```
**Why it exists**: Production secrets storage

### **app/adapters/secrets/env.py**
**Purpose**: Environment variable secrets (simple fallback)
**Contents**: Read from environment variables
**Why it exists**: Simple dev setup

---

## 📁 app/domain/ - Domain Logic (Business Rules)

**Purpose**: Core business rules isolated from infrastructure. This is pure Python with no external dependencies.

---

## 📁 app/domain/strategies/ - Strategy Pattern

### **app/domain/strategies/base.py**
**Purpose**: Base strategy interface
**Contents**:
```python
from abc import ABC, abstractmethod

class BaseRemediationStrategy(ABC):
    @abstractmethod
    def should_auto_fix(self, analysis: AnalysisResult) -> bool:
        """Decide if incident should be auto-fixed"""
        pass
```
**Why it exists**: Strategy pattern for pluggable decision logic

### **app/domain/strategies/slack_first.py**
**Purpose**: Slack-first strategy
**Contents**:
- Prefer Slack-sourced solutions
- Lower confidence threshold for Slack sources
**Example**:
```python
class SlackFirstStrategy(BaseRemediationStrategy):
    def should_auto_fix(self, analysis: AnalysisResult) -> bool:
        # If solution came from Slack thread
        if any(s["source"] == "slack" for s in analysis.similar_incidents):
            return analysis.confidence >= 0.90
        return analysis.confidence >= 0.95
```
**Why it exists**: Trust human-verified solutions from Slack more

### **app/domain/strategies/vector_db.py**
**Purpose**: Vector DB strategy
**Contents**:
- Rely on vector similarity
- Higher confidence threshold
**Why it exists**: Conservative approach based on historical data

### **app/domain/strategies/hybrid.py**
**Purpose**: Hybrid strategy combining Slack + Vector
**Contents**: Weighted decision based on both sources
**Why it exists**: Best of both worlds

### **app/domain/strategies/conservative.py**
**Purpose**: Conservative strategy for production
**Contents**:
- Very high confidence threshold (95%+)
- Only well-tested fix types
**Why it exists**: Production safety

### **app/domain/strategies/factory.py**
**Purpose**: Strategy factory
**Contents**:
- Select strategy based on environment
- Select strategy based on incident type
**Example**:
```python
class StrategyFactory:
    def get_strategy(self, environment: str) -> BaseRemediationStrategy:
        if environment == "prod":
            return ConservativeStrategy()
        elif environment == "staging":
            return HybridStrategy()
        else:
            return SlackFirstStrategy()
```
**Why it exists**: Factory pattern for creating strategies

---

## 📁 app/domain/remediators/ - Remediation Actions

### **app/domain/remediators/base.py**
**Purpose**: Base remediation action
**Contents**:
```python
from abc import ABC, abstractmethod

class BaseRemediationAction(ABC):
    @abstractmethod
    async def execute(self, incident: Incident) -> RemediationResult:
        """Execute remediation action"""
        pass
    
    @abstractmethod
    def estimate_duration(self) -> int:
        """Estimate duration in seconds"""
        pass
    
    @abstractmethod
    def risk_level(self) -> str:
        """Return risk level: low, medium, high"""
        pass
```
**Why it exists**: Strategy pattern for remediation actions

### **app/domain/remediators/github_rerun.py**
**Purpose**: Rerun GitHub workflow
**Contents**:
```python
class GitHubRerunAction(BaseRemediationAction):
    async def execute(self, incident: Incident) -> RemediationResult:
        # Extract repo and run_id from incident context
        repo = incident.context["repository"]
        run_id = incident.context["run_id"]
        
        # Rerun workflow via GitHub API
        await self.github_client.rerun_workflow(repo, run_id)
        
        # Wait for workflow to complete (with timeout)
        result = await self._wait_for_completion(repo, run_id, timeout=300)
        
        return RemediationResult(
            success=result.conclusion == "success",
            duration_seconds=result.duration
        )
```
**Why it exists**: Rerun transient failures

### **app/domain/remediators/github_secret_rotate.py**
**Purpose**: Rotate expired credentials in GitHub secrets
**Contents**: Update GitHub repository secret
**Why it exists**: Fix expired credential issues

### **app/domain/remediators/argocd_sync.py**
**Purpose**: Trigger ArgoCD application sync
**Contents**: Call ArgoCD sync API
**Why it exists**: Fix out-of-sync applications

### **app/domain/remediators/argocd_rollback.py**
**Purpose**: Rollback ArgoCD application
**Contents**: Rollback to previous revision
**Why it exists**: Rollback bad deployments

### **app/domain/remediators/k8s_restart_pod.py**
**Purpose**: Restart Kubernetes pod
**Contents**: Delete pod (deployment recreates it)
**Why it exists**: Fix pods stuck in bad state

### **app/domain/remediators/k8s_scale.py**
**Purpose**: Scale Kubernetes deployment
**Contents**: Scale replicas up/down
**Why it exists**: Fix resource contention

### **app/domain/remediators/k8s_update_image.py**
**Purpose**: Update container image
**Contents**: Update deployment image tag
**Why it exists**: Fix image pull errors

### **app/domain/remediators/docker_clear_cache.py**
**Purpose**: Clear Docker build cache
**Contents**: Trigger workflow with no-cache flag
**Why it exists**: Fix cached layer issues

### **app/domain/remediators/noop.py**
**Purpose**: No-op action for testing
**Contents**: Does nothing, always succeeds
**Why it exists**: Testing and dry-run mode

### **app/domain/remediators/factory.py**
**Purpose**: Remediation action factory
**Contents**:
```python
class RemediationActionFactory:
    def create_action(self, failure_type: str) -> BaseRemediationAction:
        actions = {
            "imagepullbackoff": K8sRestartPodAction(),
            "oomkilled": K8sScaleAction(),
            "crashloop": K8sRestartPodAction(),
            "buildcacheerror": DockerClearCacheAction(),
            "githubaction_transient": GitHubRerunAction()
        }
        return actions.get(failure_type, NoOpAction())
```
**Why it exists**: Factory pattern - select action based on failure type

---

## 📁 app/domain/validators/ - Validation Rules

### **app/domain/validators/base.py**
**Purpose**: Base validator interface
**Contents**: `BaseValidator` with validate method
**Why it exists**: Strategy pattern for validators

### **app/domain/validators/pre_remediation.py**
**Purpose**: Pre-flight checks before remediation
**Contents**:
- Check if action is safe to execute
- Check cluster health
- Check recent activity
**Example**:
```python
class PreRemediationValidator(BaseValidator):
    def validate(self, incident: Incident, plan: RemediationPlan) -> ValidationResult:
        checks = [
            self._check_blast_radius(incident),
            self._check_cluster_health(incident),
            self._check_not_blacklisted(incident, plan)
        ]
        
        passed = all(c.passed for c in checks)
        return ValidationResult(passed=passed, checks=checks)
```
**Why it exists**: Safety checks before execution

### **app/domain/validators/post_remediation.py**
**Purpose**: Health checks after remediation
**Contents**:
- Check if incident is resolved
- Check for new failures
- Check service metrics
**Why it exists**: Verify fix worked

### **app/domain/validators/blast_radius.py**
**Purpose**: Blast radius validation
**Contents**:
- Check recent fix count per service
- Enforce rate limits (max 10 fixes/hour)
**Example**:
```python
class BlastRadiusValidator(BaseValidator):
    def validate(self, incident: Incident) -> ValidationResult:
        # Count fixes in last hour for this service
        recent_fixes = self.incident_repo.count_fixes_last_hour(
            service=incident.context["service"]
        )
        
        if recent_fixes >= MAX_FIXES_PER_HOUR:
            return ValidationResult(
                passed=False,
                message=f"Blast radius limit reached: {recent_fixes} fixes in last hour"
            )
        
        return ValidationResult(passed=True)
```
**Why it exists**: Prevent runaway automation

### **app/domain/validators/safety.py**
**Purpose**: Safety guardrails
**Contents**:
- Check if action is allowed in this environment
- Check time windows (no auto-fix during peak hours?)
**Why it exists**: Additional safety checks

---

## 📁 app/domain/rules/ - Business Rules Engine

### **app/domain/rules/base.py**
**Purpose**: Base rule interface
**Contents**: `BaseRule` with evaluate method
**Why it exists**: Rules engine pattern

### **app/domain/rules/confidence.py**
**Purpose**: Confidence threshold rules
**Contents**:
- Different thresholds per environment
- Different thresholds per fix type
**Example**:
```python
class ConfidenceRule(BaseRule):
    def evaluate(self, analysis: AnalysisResult, context: ExecutionContext) -> bool:
        threshold = {
            "prod": 0.95,
            "staging": 0.85,
            "dev": 0.75
        }[context.environment]
        
        return analysis.confidence >= threshold
```
**Why it exists**: Configurable confidence thresholds

### **app/domain/rules/environment.py**
**Purpose**: Environment-specific rules
**Contents**:
- Prod requires approval
- Dev auto-fixes everything
**Why it exists**: Different rules per environment

### **app/domain/rules/time_window.py**
**Purpose**: Time-based rules
**Contents**:
- No auto-fix during peak hours
- No auto-fix on weekends (optional)
**Why it exists**: Reduce risk during high-traffic periods

### **app/domain/rules/blast_radius.py**
**Purpose**: Blast radius rules
**Contents**: Max fixes per hour per service
**Why it exists**: Rate limiting

### **app/domain/rules/blacklist.py**
**Purpose**: Blacklisted combinations
**Contents**:
- Certain fix types never auto-executed
- Certain services never auto-fixed
**Example**:
```python
class BlacklistRule(BaseRule):
    BLACKLISTED_COMBINATIONS = [
        ("payment-service", "k8s_scale"),  # Never auto-scale payment service
        ("database", "*"),  # Never auto-fix database issues
    ]
    
    def evaluate(self, incident: Incident, plan: RemediationPlan) -> bool:
        service = incident.context.get("service")
        action = plan.action_type
        
        for blacklisted_service, blacklisted_action in self.BLACKLISTED_COMBINATIONS:
            if (service == blacklisted_service and 
                (blacklisted_action == "*" or action == blacklisted_action)):
                return False
        
        return True
```
**Why it exists**: Hard-coded safety rules

---

## 📁 app/domain/parsers/ - Log Parsers

### **app/domain/parsers/base.py**
**Purpose**: Base log parser
**Contents**:
```python
from abc import ABC, abstractmethod

class BaseLogParser(ABC):
    @abstractmethod
    def can_parse(self, log: str) -> bool:
        """Check if this parser can handle the log"""
        pass
    
    @abstractmethod
    def parse(self, log: str) -> dict:
        """Parse log and extract structured data"""
        pass
```
**Why it exists**: Chain of Responsibility pattern

### **app/domain/parsers/github_actions.py**
**Purpose**: Parse GitHub Actions logs
**Contents**:
- Extract step name
- Extract error message
- Extract line numbers
**Example**:
```python
class GitHubActionsParser(BaseLogParser):
    def can_parse(self, log: str) -> bool:
        return "##[error]" in log or "Run" in log
    
    def parse(self, log: str) -> dict:
        # Extract error from GitHub Actions log format
        lines = log.split("\n")
        errors = [line for line in lines if "##[error]" in line]
        
        return {
            "errors": errors,
            "failed_step": self._extract_failed_step(log),
            "command": self._extract_command(log)
        }
```
**Why it exists**: GitHub-specific log parsing

### **app/domain/parsers/argocd.py**
**Purpose**: Parse ArgoCD logs
**Contents**: Extract sync errors
**Why it exists**: ArgoCD-specific log parsing

### **app/domain/parsers/kubernetes.py**
**Purpose**: Parse Kubernetes logs
**Contents**: Extract pod errors, reasons
**Why it exists**: K8s-specific log parsing

### **app/domain/parsers/docker.py**
**Purpose**: Parse Docker build logs
**Contents**: Extract build errors
**Why it exists**: Docker-specific log parsing

### **app/domain/parsers/chain.py**
**Purpose**: Chain of Responsibility for parsers
**Contents**:
```python
class ParserChain:
    def __init__(self, parsers: List[BaseLogParser]):
        self.parsers = parsers
    
    def parse(self, log: str) -> dict:
        for parser in self.parsers:
            if parser.can_parse(log):
                return parser.parse(log)
        
        return {"raw_log": log}  # Fallback
```
**Why it exists**: Try parsers in sequence until one works

---

*Due to length, I need to continue with utils, tests, scripts, infrastructure in a third part. Should I continue?*
