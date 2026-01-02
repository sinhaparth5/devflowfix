# Webhook API Documentation

## Overview

The Webhook API provides endpoints for receiving and processing webhook events from GitHub and GitLab. Webhooks are automatically managed by DevFlowFix - they are created when repositories are connected and deleted when repositories are disconnected.

**Base URL:** `https://api.devflowfix.com/api/v2`

## Endpoints

### POST /webhooks/github

Universal endpoint for receiving GitHub webhook events.

**Authentication:** Webhook signature verification (HMAC SHA-256)

#### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-GitHub-Event` | Yes | Event type (workflow_run, pull_request, push) |
| `X-Hub-Signature-256` | Yes | HMAC signature for verification |
| `X-GitHub-Delivery` | Yes | Unique delivery ID |
| `Content-Type` | Yes | application/json |

#### Request Body

GitHub webhook payload (varies by event type). See [GitHub Webhook Documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads).

**Example (workflow_run event):**
```json
{
  "action": "completed",
  "workflow_run": {
    "id": 123456789,
    "run_number": 42,
    "name": "CI",
    "workflow_id": 987654,
    "event": "push",
    "status": "completed",
    "conclusion": "failure",
    "head_branch": "main",
    "head_sha": "abc123def456",
    "head_commit": {
      "message": "Fix authentication bug",
      "author": {
        "name": "John Doe"
      }
    },
    "run_started_at": "2025-01-02T10:00:00Z",
    "html_url": "https://github.com/owner/repo/actions/runs/123456789",
    "logs_url": "https://api.github.com/repos/owner/repo/actions/runs/123456789/logs"
  },
  "repository": {
    "id": 111222333,
    "full_name": "owner/repo",
    "name": "repo"
  }
}
```

#### Response

**Success (200 OK):**
```json
{
  "status": "ok",
  "action": "incident_created",
  "incident_id": "INC-A1B2C3D4",
  "workflow_run_id": "123456789"
}
```

**Success - Repository not connected (200 OK):**
```json
{
  "status": "ok",
  "message": "Repository not connected"
}
```

**Error - Invalid signature (401 Unauthorized):**
```json
{
  "detail": "Invalid webhook signature"
}
```

**Error - Invalid payload (400 Bad Request):**
```json
{
  "detail": "Invalid JSON payload"
}
```

**Error - Missing repository (400 Bad Request):**
```json
{
  "detail": "Missing repository information in payload"
}
```

#### Processing Flow

1. Extract `repository.full_name` from payload
2. Look up repository connection in database
3. Decrypt webhook secret
4. Verify HMAC signature using constant-time comparison
5. Update `webhook_last_delivery_at` timestamp
6. Route to appropriate event processor
7. Return 200 OK

#### Event Processors

**workflow_run (action: completed):**
- Creates/updates `WorkflowRunTable` record
- If conclusion = "failure", creates `IncidentTable` record
- Returns incident ID if created

**pull_request:**
- Logs PR event for future tracking
- Returns success status

**push:**
- Logs push event for future tracking
- Returns success status

### POST /webhooks/gitlab

Universal endpoint for receiving GitLab webhook events.

**Authentication:** Token verification

#### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Gitlab-Event` | Yes | Event type (Pipeline Hook, Merge Request Hook, Push Hook) |
| `X-Gitlab-Token` | Yes | Webhook token for verification |
| `Content-Type` | Yes | application/json |

#### Request Body

GitLab webhook payload (varies by event type). See [GitLab Webhook Documentation](https://docs.gitlab.com/ee/user/project/integrations/webhooks.html).

**Example (Pipeline Hook):**
```json
{
  "object_kind": "pipeline",
  "object_attributes": {
    "id": 789456,
    "status": "failed",
    "ref": "main",
    "sha": "xyz789abc123"
  },
  "project": {
    "id": 444555666,
    "path_with_namespace": "group/project",
    "name": "project"
  }
}
```

#### Response

**Success (200 OK):**
```json
{
  "status": "ok",
  "event_type": "Pipeline Hook"
}
```

**Error - Invalid token (401 Unauthorized):**
```json
{
  "detail": "Invalid webhook token"
}
```

**Error - Missing project (400 Bad Request):**
```json
{
  "detail": "Missing project information in payload"
}
```

## Security

### Signature Verification

#### GitHub (HMAC SHA-256)

GitHub signs webhook payloads using HMAC SHA-256:

```python
import hmac
import hashlib

# Verify signature
expected_signature = "sha256=" + hmac.new(
    key=webhook_secret.encode(),
    msg=payload_bytes,
    digestmod=hashlib.sha256
).hexdigest()

# Use constant-time comparison
is_valid = hmac.compare_digest(expected_signature, received_signature)
```

**Header Format:**
```
X-Hub-Signature-256: sha256=<hex_digest>
```

#### GitLab (Token Verification)

GitLab uses simple token verification:

```python
# Verify token
is_valid = hmac.compare_digest(received_token, webhook_secret)
```

**Header Format:**
```
X-Gitlab-Token: <webhook_secret>
```

### Secret Management

- **Encryption:** All webhook secrets are encrypted at rest using Fernet encryption
- **Storage:** Only encrypted secrets are stored in the database
- **Access:** Secrets are decrypted only when needed for verification
- **Rotation:** Secrets are regenerated when repositories are reconnected

### Data Isolation

Webhooks are routed to the correct user based on repository ownership:

1. Extract `repository.full_name` from payload
2. Query `RepositoryConnectionTable` for matching repository
3. Extract `user_id` from repository connection
4. Create incidents/events scoped to that user

**This ensures users can only receive webhooks for their own repositories.**

## Error Handling

### Graceful Degradation

DevFlowFix returns 200 OK even for some errors to prevent GitHub/GitLab from retrying:

```python
try:
    # Process webhook
    ...
except Exception as e:
    logger.error("webhook_processing_error", error=str(e))
    # Return 200 to prevent retries
    return {"status": "error", "message": str(e)}
```

### Retry Behavior

**GitHub:**
- Retries on 5xx errors and timeouts
- Max 3 attempts over 30 minutes
- Exponential backoff

**GitLab:**
- Retries on 5xx errors
- No retries on 4xx errors

## Rate Limiting

**Current Limits:**
- No explicit rate limit (trusts GitHub/GitLab throttling)
- Future: May add per-repository rate limiting

**GitHub sends webhooks at:**
- ~100 events/minute for busy repositories
- Delivery within seconds of event occurring

## Monitoring

### Metrics

Track webhook health using these database fields:

```sql
-- Last successful webhook delivery
SELECT
    repository_full_name,
    webhook_last_delivery_at
FROM repository_connections
WHERE webhook_status = 'active';

-- Webhook delivery lag (should be < 1 minute)
SELECT
    repository_full_name,
    NOW() - webhook_last_delivery_at AS delivery_lag
FROM repository_connections
WHERE webhook_status = 'active'
ORDER BY delivery_lag DESC;
```

### Logging

All webhook events are logged with structured logging:

```python
logger.info(
    "github_webhook_received",
    event_type=event_type,
    delivery_id=delivery_id,
)

logger.info(
    "incident_created_from_webhook",
    incident_id=incident_id,
    workflow_run_id=workflow_run.id,
    repository=repo_conn.repository_full_name,
)
```

## Testing

### Testing Webhooks Locally

Use `ngrok` to expose local development server:

```bash
# 1. Start ngrok
ngrok http 8000

# 2. Update webhook URL in GitHub
https://<ngrok-id>.ngrok.io/api/v2/webhooks/github

# 3. Trigger workflow in GitHub
# 4. Check DevFlowFix logs for webhook delivery
```

### Testing with curl

```bash
# Generate signature
PAYLOAD='{"repository":{"full_name":"owner/repo"},"action":"completed"}'
SECRET="your_webhook_secret"
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

# Send webhook
curl -X POST http://localhost:8000/api/v2/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: workflow_run" \
  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
  -H "X-GitHub-Delivery: test-delivery-1" \
  -d "$PAYLOAD"
```

### Unit Test Example

```python
def test_github_webhook_signature_verification():
    """Test GitHub signature verification."""
    payload = b'{"action": "completed"}'
    secret = "test_secret"

    # Generate valid signature
    signature = "sha256=" + hmac.new(
        key=secret.encode(),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    # Verify
    is_valid = WebhookManager.verify_github_signature(
        payload=payload,
        signature=signature,
        secret=secret,
    )

    assert is_valid is True
```

## Database Schema

### repository_connections

Webhook-related fields:

| Column | Type | Description |
|--------|------|-------------|
| `webhook_id` | VARCHAR(100) | GitHub/GitLab webhook ID |
| `webhook_url` | VARCHAR(500) | Webhook endpoint URL |
| `webhook_secret` | VARCHAR(512) | Encrypted webhook secret |
| `webhook_events` | JSON | Subscribed events array |
| `webhook_status` | VARCHAR(50) | Status: active/inactive/failed |
| `webhook_created_at` | TIMESTAMP | Webhook creation time |
| `webhook_last_delivery_at` | TIMESTAMP | Last successful delivery |

### workflow_runs

Created/updated by webhook events:

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(50) | Primary key |
| `repository_connection_id` | VARCHAR(50) | Foreign key to repository_connections |
| `run_id` | VARCHAR(50) | GitHub run ID |
| `workflow_name` | VARCHAR(255) | Workflow name |
| `status` | VARCHAR(50) | Status: completed, in_progress, queued |
| `conclusion` | VARCHAR(50) | Conclusion: success, failure, cancelled |
| `branch` | VARCHAR(255) | Branch name |
| `commit_sha` | VARCHAR(255) | Commit SHA |

### incidents

Created when workflows fail:

| Column | Type | Description |
|--------|------|-------------|
| `incident_id` | VARCHAR(50) | Unique incident ID (INC-XXXXXXXX) |
| `user_id` | VARCHAR(50) | User who owns the repository |
| `workflow_run_id` | VARCHAR(50) | Foreign key to workflow_runs |
| `repository` | VARCHAR(255) | Repository full name |
| `severity` | VARCHAR(50) | Severity: high, medium, low |
| `status` | VARCHAR(50) | Status: open, investigating, resolved |
| `source` | VARCHAR(50) | Source: webhook, manual, api |

## Examples

### Complete GitHub Workflow Failure Flow

**1. Workflow fails in GitHub:**
```
GitHub Actions: Workflow "CI" fails on main branch
```

**2. GitHub sends webhook:**
```http
POST https://api.devflowfix.com/api/v2/webhooks/github
X-GitHub-Event: workflow_run
X-Hub-Signature-256: sha256=abc123...
X-GitHub-Delivery: 12345-67890
Content-Type: application/json

{
  "action": "completed",
  "workflow_run": {
    "id": 123456789,
    "conclusion": "failure",
    ...
  },
  "repository": {
    "full_name": "owner/repo"
  }
}
```

**3. DevFlowFix processes webhook:**
```python
# Look up repository
repo_conn = db.query(RepositoryConnectionTable).filter(
    repository_full_name == "owner/repo"
).first()

# Verify signature
webhook_secret = decrypt(repo_conn.webhook_secret)
is_valid = verify_signature(payload, signature, webhook_secret)

# Create workflow run
workflow_run = WorkflowRunTable(...)
db.add(workflow_run)

# Create incident (conclusion = failure)
incident = IncidentTable(
    user_id=repo_conn.user_id,
    workflow_run_id=workflow_run.id,
    ...
)
db.add(incident)
```

**4. DevFlowFix responds:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok",
  "action": "incident_created",
  "incident_id": "INC-A1B2C3D4",
  "workflow_run_id": "123456789"
}
```

**5. User sees incident:**
```http
GET /api/v2/incidents
Authorization: Bearer <jwt_token>

Response:
[
  {
    "incident_id": "INC-A1B2C3D4",
    "repository": "owner/repo",
    "workflow_name": "CI",
    "status": "open",
    "severity": "high",
    "created_at": "2025-01-02T10:00:00Z"
  }
]
```

## Related Endpoints

### Repository Management

See [Repository API Documentation](./repositories.md) for:

- `POST /api/v2/repositories/connect` - Connect repository (auto-creates webhook)
- `DELETE /api/v2/repositories/connections/{id}` - Disconnect repository (auto-deletes webhook)
- `GET /api/v2/repositories/connections/{id}` - Get webhook status

### Incident Management

See [Incident API Documentation](./incidents.md) for:

- `GET /api/v2/incidents` - List incidents created from webhooks
- `GET /api/v2/incidents/{id}` - Get incident details
- `PATCH /api/v2/incidents/{id}` - Update incident status

## Changelog

### v2.0 (2025-01-02)

- **NEW:** Automatic webhook management
- **NEW:** Universal webhook endpoints for GitHub and GitLab
- **NEW:** Webhook signature verification
- **NEW:** Incident creation from failed workflows
- **IMPROVED:** Webhook secret encryption at rest
- **IMPROVED:** Graceful error handling

### v1.0 (2024-12-01)

- Initial webhook support (manual configuration required)
