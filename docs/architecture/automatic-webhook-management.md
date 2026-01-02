# Automatic Webhook Management Implementation Plan

**Version:** 1.0
**Date:** 2025-01-02
**Status:** Planning
**Authors:** DevFlowFix Team

---

## Table of Contents

1. [Overview](#overview)
2. [Goals and Requirements](#goals-and-requirements)
3. [Architecture Design](#architecture-design)
4. [Database Schema](#database-schema)
5. [Implementation Phases](#implementation-phases)
6. [Security Considerations](#security-considerations)
7. [Error Handling](#error-handling)
8. [Testing Strategy](#testing-strategy)
9. [Deployment Considerations](#deployment-considerations)
10. [API Endpoints](#api-endpoints)
11. [Webhook Processing Flow](#webhook-processing-flow)

---

## Overview

### Current Problem

Users must manually:
- Configure webhook URLs in their GitHub/GitLab repositories
- Set up webhook secrets
- Select which events to monitor
- Manage webhook lifecycle (updates, deletions)

This creates friction and reduces user adoption.

### Proposed Solution

**Automatic webhook management** - When a user connects a repository via OAuth, the system automatically:
1. Creates a webhook on that repository (via GitHub/GitLab API)
2. Configures it to point to our universal webhook endpoint
3. Stores webhook metadata for verification and management
4. Handles webhook events and routes them to the correct user
5. Cleans up webhooks when repository is disconnected

### Benefits

✅ **Zero-configuration UX** - User just clicks "Connect Repository"
✅ **Real-time monitoring** - Instant notifications when workflows fail
✅ **Scalable architecture** - One endpoint serves all users/repos
✅ **Industry standard** - How Vercel, Netlify, CircleCI work
✅ **Automatic cleanup** - No orphaned webhooks

---

## Goals and Requirements

### Functional Requirements

1. **FR-1:** Automatically create webhook when user connects repository
2. **FR-2:** Store webhook metadata (ID, secret, URL) in database
3. **FR-3:** Process incoming webhook events and route to correct user
4. **FR-4:** Create incidents automatically when workflows fail
5. **FR-5:** Update workflow run status in real-time
6. **FR-6:** Automatically delete webhook when user disconnects repository
7. **FR-7:** Support both GitHub and GitLab (initially GitHub only)
8. **FR-8:** Handle webhook signature verification for security

### Non-Functional Requirements

1. **NFR-1:** Webhook processing latency < 500ms
2. **NFR-2:** Support 1000+ concurrent webhook events
3. **NFR-3:** 99.9% webhook delivery success rate
4. **NFR-4:** Idempotent webhook processing (handle duplicates)
5. **NFR-5:** Comprehensive logging and monitoring
6. **NFR-6:** Graceful degradation if webhook creation fails

### Technical Requirements

1. **TR-1:** OAuth token must have `admin:repo_hook` or `repo` scope
2. **TR-2:** Webhook endpoint must be publicly accessible (HTTPS)
3. **TR-3:** Database must store webhook_id for cleanup
4. **TR-4:** Each webhook must have unique secret for verification
5. **TR-5:** Support ngrok/Cloudflare Tunnel for local development

---

## Architecture Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Action                             │
│  User connects repository: "octocat/Hello-World"                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DevFlowFix Backend                           │
│  1. Verify OAuth token has webhook permissions                  │
│  2. Generate unique webhook secret                              │
│  3. Call GitHub API: POST /repos/octocat/Hello-World/hooks      │
│  4. Store webhook_id + secret in database                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub                                  │
│  Webhook created:                                               │
│  - URL: https://api.devflowfix.com/webhooks/github             │
│  - Events: workflow_run, pull_request, push                     │
│  - Secret: <unique-per-repo>                                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Workflow Execution                           │
│  User pushes code → GitHub Actions runs → Workflow fails        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Webhook Event                         │
│  POST https://api.devflowfix.com/webhooks/github                │
│  Headers:                                                       │
│    X-GitHub-Event: workflow_run                                 │
│    X-Hub-Signature-256: sha256=...                              │
│  Body:                                                          │
│    {                                                            │
│      "repository": { "full_name": "octocat/Hello-World" },     │
│      "workflow_run": { "conclusion": "failure", ... }          │
│    }                                                            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                 Webhook Processing (DevFlowFix)                 │
│  1. Extract repository: "octocat/Hello-World"                   │
│  2. Query DB: Get repository_connection by full_name            │
│  3. Retrieve webhook_secret for this connection                 │
│  4. Verify signature using secret                               │
│  5. Extract user_id from repository_connection                  │
│  6. Create WorkflowRun record for user                          │
│  7. If failure: Create Incident for user                        │
│  8. Send real-time notification (WebSocket/SSE)                 │
│  9. Respond 200 OK to GitHub                                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                      User Dashboard                             │
│  User sees:                                                     │
│  - New incident appears in real-time                            │
│  - Workflow run status updated                                  │
│  - Notification: "Workflow failed on main branch"               │
└─────────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        API Layer                                 │
│                                                                  │
│  ┌────────────────────┐    ┌──────────────────────┐            │
│  │ Repository API     │    │ Webhook API          │            │
│  │ /repositories      │    │ /webhooks/github     │            │
│  │                    │    │ /webhooks/gitlab     │            │
│  │ - connect()        │    │                      │            │
│  │ - disconnect()     │    │ - process_event()    │            │
│  └────────────────────┘    └──────────────────────┘            │
│           │                          │                          │
└───────────┼──────────────────────────┼──────────────────────────┘
            │                          │
            ↓                          ↓
┌──────────────────────────────────────────────────────────────────┐
│                     Service Layer                                │
│                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │ WebhookManager      │  │ WebhookProcessor    │              │
│  │                     │  │                     │              │
│  │ - create_webhook()  │  │ - verify_signature()│              │
│  │ - delete_webhook()  │  │ - route_to_user()   │              │
│  │ - update_webhook()  │  │ - create_incident() │              │
│  └─────────────────────┘  └─────────────────────┘              │
│           │                          │                          │
└───────────┼──────────────────────────┼──────────────────────────┘
            │                          │
            ↓                          ↓
┌──────────────────────────────────────────────────────────────────┐
│                   External Services                              │
│                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │ GitHubOAuthProvider │  │ TokenManager        │              │
│  │                     │  │                     │              │
│  │ - create_webhook()  │  │ - get_oauth_token() │              │
│  │ - delete_webhook()  │  │ - decrypt_token()   │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
            │
            ↓
┌──────────────────────────────────────────────────────────────────┐
│                      GitHub API                                  │
│                                                                  │
│  POST   /repos/{owner}/{repo}/hooks                              │
│  GET    /repos/{owner}/{repo}/hooks/{hook_id}                    │
│  DELETE /repos/{owner}/{repo}/hooks/{hook_id}                    │
│  PATCH  /repos/{owner}/{repo}/hooks/{hook_id}                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Updated Repository Connection Table

```sql
CREATE TABLE repository_connections (
    -- Existing fields
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id),
    provider VARCHAR(50) NOT NULL,  -- 'github', 'gitlab'
    repository_full_name VARCHAR(255) NOT NULL,
    repository_name VARCHAR(255),
    default_branch VARCHAR(255),
    is_private BOOLEAN DEFAULT false,
    is_enabled BOOLEAN DEFAULT true,

    -- NEW: Webhook management fields
    webhook_id VARCHAR(255),  -- GitHub/GitLab webhook ID
    webhook_secret VARCHAR(512),  -- Encrypted webhook secret
    webhook_url TEXT,  -- Full webhook URL
    webhook_events TEXT[],  -- Array: ['workflow_run', 'pull_request', 'push']
    webhook_created_at TIMESTAMP WITH TIME ZONE,
    webhook_last_delivery_at TIMESTAMP WITH TIME ZONE,
    webhook_status VARCHAR(50),  -- 'active', 'inactive', 'failed'

    -- Existing fields
    auto_pr_enabled BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes
    UNIQUE(user_id, repository_full_name),
    INDEX idx_repo_full_name (repository_full_name),
    INDEX idx_webhook_id (webhook_id)
);
```

### Webhook Delivery Log Table (Optional - for debugging)

```sql
CREATE TABLE webhook_deliveries (
    id VARCHAR(255) PRIMARY KEY,
    repository_connection_id VARCHAR(255) REFERENCES repository_connections(id),
    event_type VARCHAR(100),  -- 'workflow_run', 'pull_request', etc.
    delivery_id VARCHAR(255),  -- GitHub delivery ID
    payload JSONB,
    signature_verified BOOLEAN,
    processing_status VARCHAR(50),  -- 'success', 'failed', 'skipped'
    error_message TEXT,
    processing_duration_ms INTEGER,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,

    INDEX idx_repo_conn (repository_connection_id),
    INDEX idx_received_at (received_at DESC)
);
```

---

## Implementation Phases

### Phase 1: Database & Core Infrastructure (Day 1)

**Tasks:**
1. Add webhook fields to `RepositoryConnectionTable` model
2. Create database migration
3. Update repository connection schemas
4. Add webhook secret encryption/decryption utilities

**Deliverables:**
- ✅ Database schema updated
- ✅ Models updated with webhook fields
- ✅ Migration scripts ready

**Files to modify:**
- `app/adapters/database/postgres/models.py`
- `app/core/schemas/repository.py`
- `alembic/versions/XXX_add_webhook_fields.py`

---

### Phase 2: Webhook Manager Service (Day 2)

**Tasks:**
1. Create `WebhookManager` service class
2. Implement `create_webhook()` method
3. Implement `delete_webhook()` method
4. Implement `update_webhook()` method
5. Add webhook secret generation
6. Add error handling and retries

**Deliverables:**
- ✅ `app/services/webhook/webhook_manager.py` created
- ✅ GitHub webhook creation working
- ✅ GitLab webhook creation working
- ✅ Unit tests for webhook manager

**Key Methods:**
```python
class WebhookManager:
    async def create_webhook(
        db: Session,
        repository_connection_id: str,
        webhook_base_url: str,
    ) -> Dict[str, Any]

    async def delete_webhook(
        db: Session,
        repository_connection_id: str,
    ) -> bool

    async def verify_webhook_signature(
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool
```

---

### Phase 3: Auto-Create on Repository Connect (Day 3)

**Tasks:**
1. Modify `POST /repositories/connect` endpoint
2. Auto-create webhook after repository connection
3. Handle webhook creation failures gracefully
4. Update response to include webhook status
5. Add logging for webhook operations

**Deliverables:**
- ✅ Repository connect auto-creates webhook
- ✅ Graceful degradation if webhook fails
- ✅ User notified of webhook status

**Endpoint Changes:**
```python
@router.post("/repositories/connect")
async def connect_repository(...):
    # 1. Create repository connection (existing)
    repo_conn = create_repository_connection(...)

    # 2. AUTO-CREATE WEBHOOK (new)
    try:
        webhook_result = await webhook_manager.create_webhook(
            db=db,
            repository_connection_id=repo_conn.id,
            webhook_base_url=settings.webhook_base_url,
        )
        repo_conn.webhook_id = webhook_result["id"]
        repo_conn.webhook_status = "active"
    except Exception as e:
        logger.error("webhook_creation_failed", error=str(e))
        repo_conn.webhook_status = "failed"
        # Continue - repository still connected

    # 3. Return response with webhook status
    return {
        "repository": repo_conn,
        "webhook_status": repo_conn.webhook_status,
    }
```

---

### Phase 4: Webhook Processing Endpoint (Day 4)

**Tasks:**
1. Create universal webhook endpoint
2. Implement signature verification
3. Implement repository-to-user lookup
4. Route events to correct processors
5. Handle `workflow_run` events
6. Handle `pull_request` events
7. Handle `push` events

**Deliverables:**
- ✅ `POST /webhooks/github` endpoint working
- ✅ Signature verification implemented
- ✅ Events routed to correct user
- ✅ Incidents created for workflow failures

**Endpoint Structure:**
```python
@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    # 1. Extract repository from payload
    payload = await request.json()
    repo_full_name = payload["repository"]["full_name"]

    # 2. Look up repository connection
    repo_conn = db.query(RepositoryConnectionTable).filter(
        RepositoryConnectionTable.repository_full_name == repo_full_name
    ).first()

    if not repo_conn:
        return {"error": "Repository not connected"}

    # 3. Verify signature
    signature = request.headers.get("X-Hub-Signature-256")
    await verify_signature(
        payload=await request.body(),
        signature=signature,
        secret=repo_conn.webhook_secret,
    )

    # 4. Route to appropriate processor
    event_type = request.headers.get("X-GitHub-Event")

    if event_type == "workflow_run":
        await process_workflow_run(db, payload, repo_conn)
    elif event_type == "pull_request":
        await process_pull_request(db, payload, repo_conn)

    return {"status": "ok"}
```

---

### Phase 5: Auto-Delete on Disconnect (Day 5)

**Tasks:**
1. Modify `DELETE /repositories/{id}/disconnect` endpoint
2. Auto-delete webhook before removing connection
3. Handle deletion failures gracefully
4. Clean up database records

**Deliverables:**
- ✅ Repository disconnect auto-deletes webhook
- ✅ Orphaned webhooks prevented
- ✅ Clean database state

---

### Phase 6: Testing & Documentation (Day 6-7)

**Tasks:**
1. Unit tests for all components
2. Integration tests for webhook flow
3. Test with ngrok in local environment
4. Update API documentation
5. Create user guide for webhook features
6. Add monitoring and alerts

**Deliverables:**
- ✅ 90%+ test coverage
- ✅ End-to-end tests passing
- ✅ Documentation updated
- ✅ Monitoring dashboard

---

## Security Considerations

### 1. Webhook Signature Verification

**Requirement:** Verify all incoming webhook requests are from GitHub/GitLab

**Implementation:**
```python
import hmac
import hashlib

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature.

    GitHub sends: X-Hub-Signature-256: sha256=<hash>
    """
    expected_signature = "sha256=" + hmac.new(
        key=secret.encode(),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)
```

**Security Notes:**
- Use `hmac.compare_digest()` to prevent timing attacks
- Reject requests with invalid signatures (401 Unauthorized)
- Log failed verification attempts for security monitoring

### 2. Webhook Secret Management

**Requirements:**
- Each repository connection has unique webhook secret
- Secrets stored encrypted in database
- Secrets never exposed in API responses or logs

**Implementation:**
```python
# Generate unique secret per webhook
webhook_secret = secrets.token_urlsafe(32)  # 256-bit secret

# Encrypt before storing
encrypted_secret = encryption_manager.encrypt(webhook_secret)
repo_conn.webhook_secret = encrypted_secret

# Decrypt when needed for verification
secret = encryption_manager.decrypt(repo_conn.webhook_secret)
```

### 3. Rate Limiting

**Protection against webhook spam/abuse:**
```python
# Redis-based rate limiting
@limiter.limit("100/minute")
@router.post("/webhooks/github")
async def github_webhook(...):
    ...
```

### 4. Idempotency

**Handle duplicate webhook deliveries:**
```python
# Check delivery ID to prevent duplicate processing
delivery_id = request.headers.get("X-GitHub-Delivery")

existing = db.query(WebhookDeliveryTable).filter(
    delivery_id == delivery_id
).first()

if existing:
    return {"status": "already_processed"}
```

### 5. Input Validation

**Validate all webhook payloads:**
```python
# Validate expected fields exist
required_fields = ["repository", "action", "sender"]
for field in required_fields:
    if field not in payload:
        raise HTTPException(400, f"Missing field: {field}")

# Validate repository exists in our database
repo_conn = get_repository_connection(payload["repository"]["full_name"])
if not repo_conn:
    return {"error": "Unknown repository"}
```

---

## Error Handling

### Webhook Creation Failures

**Scenarios:**
1. OAuth token lacks webhook permissions
2. Network error calling GitHub API
3. Repository doesn't exist
4. Webhook already exists

**Handling:**
```python
try:
    webhook = await github_provider.create_webhook(...)
except PermissionError:
    # OAuth token lacks admin:repo_hook scope
    logger.error("insufficient_permissions")
    return {"webhook_status": "failed", "reason": "insufficient_permissions"}
except WebhookAlreadyExistsError:
    # Webhook already exists - fetch and update
    existing_webhook = await github_provider.get_webhooks(...)
    repo_conn.webhook_id = existing_webhook["id"]
except Exception as e:
    # Network error or other failure
    logger.error("webhook_creation_failed", error=str(e))
    # Repository still connected, webhook can be created later
    repo_conn.webhook_status = "failed"
```

### Webhook Processing Failures

**Scenarios:**
1. Invalid signature
2. Malformed payload
3. Database error
4. Unknown event type

**Handling:**
```python
@router.post("/webhooks/github")
async def github_webhook(...):
    try:
        # Process webhook
        ...
    except SignatureVerificationError:
        logger.warning("invalid_signature", repo=repo_full_name)
        return JSONResponse(status_code=401, content={"error": "Invalid signature"})
    except ValidationError as e:
        logger.error("invalid_payload", error=str(e))
        return JSONResponse(status_code=400, content={"error": "Invalid payload"})
    except Exception as e:
        logger.error("webhook_processing_failed", error=str(e), exc_info=True)
        # Return 200 to prevent GitHub retries
        return {"status": "error", "message": str(e)}
```

### Retry Strategy

**GitHub Webhook Retries:**
- GitHub retries failed webhooks up to 3 times
- Return 2xx status to prevent retries
- Return 4xx/5xx only for truly bad requests

**Our Retry Strategy:**
```python
# For transient failures (DB connection, etc.)
# Return 200 and queue for async retry
if is_transient_error(error):
    await queue_for_retry(webhook_payload)
    return {"status": "queued_for_retry"}
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/services/test_webhook_manager.py
class TestWebhookManager:
    async def test_create_webhook_success(self):
        """Test successful webhook creation"""

    async def test_create_webhook_permission_denied(self):
        """Test webhook creation with insufficient permissions"""

    async def test_delete_webhook_success(self):
        """Test successful webhook deletion"""

    async def test_verify_signature_valid(self):
        """Test signature verification with valid signature"""

    async def test_verify_signature_invalid(self):
        """Test signature verification with invalid signature"""
```

### Integration Tests

```python
# tests/integration/test_webhook_flow.py
class TestWebhookFlow:
    async def test_end_to_end_workflow_failure(self):
        """
        Test complete flow:
        1. User connects repository
        2. Webhook auto-created
        3. Simulate webhook event
        4. Verify incident created
        5. User sees incident in dashboard
        """
```

### Local Testing with ngrok

**Setup:**
```bash
# 1. Start ngrok
ngrok http 8000

# 2. Update .env
WEBHOOK_BASE_URL=https://abc123.ngrok-free.app

# 3. Connect repository
# Webhook URL will be: https://abc123.ngrok-free.app/webhooks/github

# 4. Trigger workflow in GitHub
# 5. Watch logs to see webhook received
```

---

## Deployment Considerations

### Environment Variables

```bash
# .env
WEBHOOK_BASE_URL=https://api.devflowfix.com
WEBHOOK_SECRET_ENCRYPTION_KEY=<32-byte-key>
GITHUB_OAUTH_CLIENT_ID=<client-id>
GITHUB_OAUTH_CLIENT_SECRET=<client-secret>
GITLAB_OAUTH_CLIENT_ID=<client-id>
GITLAB_OAUTH_CLIENT_SECRET=<client-secret>
```

### Production Webhook URL

**Requirements:**
- HTTPS required (GitHub/GitLab won't send to HTTP)
- Publicly accessible
- Low latency (<500ms response time)
- High availability (99.9%+)

**Options:**
1. **Own domain:** `https://api.devflowfix.com/webhooks/github`
2. **Cloudflare Tunnel:** For development without public IP
3. **ngrok:** For local testing only

### Monitoring

**Key Metrics:**
- Webhook creation success rate
- Webhook processing latency (p50, p95, p99)
- Signature verification failures
- Incident creation rate
- Failed webhook deliveries

**Alerts:**
- Webhook creation failure rate > 5%
- Webhook processing latency > 1s
- Signature verification failures > 10/min
- Database errors during webhook processing

### Logging

**Log Events:**
```python
logger.info("webhook_created",
    repository=repo_full_name,
    webhook_id=webhook_id,
    events=webhook_events)

logger.info("webhook_received",
    event_type=event_type,
    repository=repo_full_name,
    delivery_id=delivery_id)

logger.error("webhook_processing_failed",
    error=str(e),
    repository=repo_full_name,
    exc_info=True)
```

---

## API Endpoints

### Modified Endpoints

#### 1. Connect Repository (Enhanced)

```
POST /api/v2/repositories/connect
```

**Request:**
```json
{
  "repository_full_name": "octocat/Hello-World"
}
```

**Response:**
```json
{
  "success": true,
  "repository": {
    "id": "conn_123",
    "repository_full_name": "octocat/Hello-World",
    "webhook_status": "active",
    "webhook_events": ["workflow_run", "pull_request", "push"],
    "webhook_created_at": "2025-01-02T10:00:00Z"
  }
}
```

#### 2. Disconnect Repository (Enhanced)

```
DELETE /api/v2/repositories/{repository_connection_id}/disconnect
```

**Response:**
```json
{
  "success": true,
  "message": "Repository disconnected and webhook removed",
  "webhook_deleted": true
}
```

### New Endpoints

#### 3. Universal GitHub Webhook

```
POST /api/v2/webhooks/github
```

**Headers:**
```
X-GitHub-Event: workflow_run
X-Hub-Signature-256: sha256=...
X-GitHub-Delivery: abc-123-def
```

**Request Body:** GitHub webhook payload (varies by event type)

**Response:**
```json
{
  "status": "ok",
  "processed": true
}
```

#### 4. Universal GitLab Webhook

```
POST /api/v2/webhooks/gitlab
```

**Headers:**
```
X-Gitlab-Event: Pipeline Hook
X-Gitlab-Token: <webhook-secret>
```

#### 5. Webhook Status

```
GET /api/v2/repositories/{repository_connection_id}/webhook/status
```

**Response:**
```json
{
  "webhook_id": "webhook_456",
  "status": "active",
  "events": ["workflow_run", "pull_request"],
  "last_delivery_at": "2025-01-02T10:30:00Z",
  "total_deliveries": 145,
  "failed_deliveries": 2
}
```

#### 6. Retry Webhook Creation

```
POST /api/v2/repositories/{repository_connection_id}/webhook/retry
```

**Use case:** Manually retry webhook creation if it failed initially

---

## Webhook Processing Flow

### GitHub `workflow_run` Event

```python
async def process_workflow_run(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
):
    """Process workflow_run webhook event"""

    workflow_run_data = payload["workflow_run"]
    action = payload["action"]  # "completed", "requested", etc.

    # Only process completed workflows
    if action != "completed":
        return

    # Create or update workflow run in database
    workflow_run = upsert_workflow_run(
        db=db,
        repository_connection_id=repo_conn.id,
        run_data=workflow_run_data,
    )

    # If workflow failed, create incident
    if workflow_run_data["conclusion"] == "failure":
        incident = create_incident(
            db=db,
            user_id=repo_conn.user_id,
            workflow_run=workflow_run,
            repository=repo_conn.repository_full_name,
        )

        # Send real-time notification
        await notify_user(
            user_id=repo_conn.user_id,
            notification_type="workflow_failed",
            data={"incident_id": incident.incident_id},
        )

    db.commit()
```

### GitHub `pull_request` Event

```python
async def process_pull_request(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
):
    """Process pull_request webhook event"""

    pr_data = payload["pull_request"]
    action = payload["action"]  # "opened", "closed", "synchronize"

    # Store PR metadata for analysis
    pr_metadata = {
        "number": pr_data["number"],
        "title": pr_data["title"],
        "state": pr_data["state"],
        "author": pr_data["user"]["login"],
        "created_at": pr_data["created_at"],
    }

    # Check if this PR was created by DevFlowFix (auto-fix)
    if "DevFlowFix" in pr_data.get("head", {}).get("ref", ""):
        # Update incident with PR status
        update_incident_pr_status(
            db=db,
            pr_number=pr_data["number"],
            pr_status=pr_data["state"],
        )
```

---

## Rollout Plan

### Phase 1: Beta Testing (Week 1)
- Deploy to staging environment
- Test with 5 internal repositories
- Monitor webhook delivery and processing
- Fix critical bugs

### Phase 2: Limited Release (Week 2)
- Enable for 10% of users
- Monitor error rates and performance
- Gather user feedback
- Iterate on UX

### Phase 3: Full Release (Week 3)
- Enable for all new repository connections
- Migrate existing connections (optional webhook creation)
- Monitor at scale
- Celebrate! 🎉

---

## Success Metrics

### Technical Metrics
- ✅ Webhook creation success rate > 95%
- ✅ Webhook processing latency < 500ms (p95)
- ✅ Incident creation within 10s of workflow failure
- ✅ Zero webhook signature verification bypasses
- ✅ Database query performance < 100ms

### User Experience Metrics
- ✅ Time to first incident notification < 30s
- ✅ User completes repository connection in < 60s
- ✅ User satisfaction score > 4.5/5
- ✅ Support tickets related to webhooks < 5%

### Business Metrics
- ✅ User activation rate increases by 30%
- ✅ Repository connection rate increases by 50%
- ✅ User retention improves due to real-time monitoring

---

## Future Enhancements

1. **Webhook Health Monitoring Dashboard**
   - Show webhook delivery success rates per repository
   - Alert on webhook failures
   - Auto-recreate failed webhooks

2. **Custom Webhook Events**
   - Allow users to select which events to monitor
   - Configure incident severity by event type

3. **Webhook Replay**
   - Replay failed webhook events for debugging
   - Manual trigger of webhook processing

4. **Multi-Provider Support**
   - GitLab webhooks (Phase 2)
   - Bitbucket webhooks (Phase 3)
   - Azure DevOps webhooks (Phase 4)

5. **Webhook Analytics**
   - Visualize webhook delivery patterns
   - Track incident creation trends
   - Workflow failure correlation analysis

---

## Appendix

### A. GitHub Webhook Events Reference

| Event | Description | Use Case |
|-------|-------------|----------|
| `workflow_run` | Workflow execution started/completed | Create incidents on failure |
| `pull_request` | PR opened/closed/merged | Track auto-fix PR status |
| `push` | Code pushed to branch | Trigger analysis |
| `check_run` | Check runs completed | Monitor CI/CD checks |
| `deployment` | Deployment created | Track deployment status |

### B. Webhook Payload Examples

**workflow_run (completed, failure):**
```json
{
  "action": "completed",
  "workflow_run": {
    "id": 123456,
    "name": "CI",
    "status": "completed",
    "conclusion": "failure",
    "head_branch": "main",
    "head_sha": "abc123",
    "run_number": 42,
    "html_url": "https://github.com/octocat/Hello-World/actions/runs/123456"
  },
  "repository": {
    "full_name": "octocat/Hello-World",
    "private": false
  }
}
```

### C. Rate Limits

**GitHub API:**
- 5000 requests/hour for authenticated requests
- Webhook creation counts toward this limit
- Monitor `X-RateLimit-Remaining` header

**Webhook Delivery:**
- GitHub retries failed webhooks 3 times
- Exponential backoff between retries
- Return 2xx to acknowledge receipt

---

## Conclusion

This implementation plan provides a comprehensive roadmap for automatic webhook management in DevFlowFix. By following this phased approach, we'll deliver a seamless user experience while maintaining security, reliability, and scalability.

**Next Steps:**
1. Review and approve this plan
2. Create implementation tickets in project management tool
3. Assign tasks to development team
4. Begin Phase 1: Database & Core Infrastructure

---

**Document History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-02 | DevFlowFix Team | Initial draft |

