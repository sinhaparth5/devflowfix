# Webhook Management Guide

## Overview

DevFlowFix automatically manages webhooks for your connected repositories. When you connect a repository, DevFlowFix creates a webhook to receive real-time notifications about CI/CD events. When you disconnect a repository, the webhook is automatically removed.

**Zero Configuration Required**: You don't need to manually configure webhooks - everything is handled automatically!

## How It Works

### 1. Automatic Webhook Creation

When you connect a repository to DevFlowFix:

1. **Authorization**: DevFlowFix uses your OAuth token to access the repository
2. **Webhook Setup**: A webhook is automatically created in your repository
3. **Secret Generation**: A secure random secret is generated for signature verification
4. **Event Subscription**: The webhook subscribes to relevant events (workflow runs, pull requests, pushes)

**Example Flow:**
```
Connect Repository → OAuth Authorization → Create Webhook → Start Monitoring
```

### 2. Automatic Webhook Deletion

When you disconnect a repository:

1. **Webhook Removal**: The webhook is deleted from GitHub/GitLab
2. **Data Cleanup**: Webhook secrets and metadata are removed from the database
3. **Graceful Handling**: Repository disconnects successfully even if webhook deletion fails

**Example Flow:**
```
Disconnect Repository → Delete Webhook → Clean Database → Confirmation
```

## Supported Events

DevFlowFix monitors the following webhook events:

### GitHub Events

| Event | Description | Use Case |
|-------|-------------|----------|
| `workflow_run` | GitHub Actions workflow execution | Detect CI/CD failures and create incidents |
| `pull_request` | Pull request activity | Track auto-fix PRs created by DevFlowFix |
| `push` | Code push to repository | Trigger analysis on new commits |

### GitLab Events

| Event | Description | Use Case |
|-------|-------------|----------|
| `pipeline_events` | GitLab CI/CD pipeline execution | Detect pipeline failures |
| `merge_requests_events` | Merge request activity | Track auto-fix MRs |
| `push_events` | Code push to repository | Trigger analysis on new commits |

## Security

### Signature Verification

All incoming webhooks are verified using cryptographic signatures:

**GitHub:** HMAC SHA-256 signature in `X-Hub-Signature-256` header
```
Expected: sha256=<hmac_hash>
Verified: Using webhook secret with constant-time comparison
```

**GitLab:** Token verification in `X-Gitlab-Token` header
```
Expected: <webhook_token>
Verified: Using constant-time comparison
```

### Secret Encryption

Webhook secrets are encrypted at rest using Fernet symmetric encryption:

- **Algorithm**: Fernet (AES-128-CBC + HMAC-SHA256)
- **Key Management**: Encryption key stored in environment variable `OAUTH_TOKEN_ENCRYPTION_KEY`
- **Storage**: Only encrypted secrets are stored in the database

### Data Isolation

Each webhook is scoped to a specific repository connection:

1. Webhook payload includes `repository.full_name`
2. DevFlowFix looks up the repository connection in the database
3. Events are routed to the correct user based on repository ownership
4. Users can only see incidents/data for their own repositories

## API Endpoints

### Connect Repository (Auto-creates Webhook)

```http
POST /api/v2/repositories/connect
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "repository_full_name": "owner/repo",
  "auto_pr_enabled": true,
  "setup_webhook": true,
  "webhook_events": ["workflow_run", "pull_request", "push"]
}
```

**Response:**
```json
{
  "id": "rpc_abc123",
  "repository_full_name": "owner/repo",
  "webhook_id": "12345",
  "webhook_url": "https://api.devflowfix.com/api/v2/webhooks/github",
  "webhook_status": "active",
  "webhook_events": ["workflow_run", "pull_request", "push"],
  "webhook_created_at": "2025-01-02T10:00:00Z"
}
```

### Disconnect Repository (Auto-deletes Webhook)

```http
DELETE /api/v2/repositories/connections/{connection_id}?delete_webhook=true
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "success": true,
  "connection_id": "rpc_abc123",
  "repository_full_name": "owner/repo",
  "webhook_deleted": true,
  "message": "Repository owner/repo successfully disconnected and webhook deleted"
}
```

### Webhook Processing Endpoints

**GitHub Webhook:**
```http
POST /api/v2/webhooks/github
X-GitHub-Event: workflow_run
X-Hub-Signature-256: sha256=<signature>
X-GitHub-Delivery: <delivery_id>
```

**GitLab Webhook:**
```http
POST /api/v2/webhooks/gitlab
X-Gitlab-Event: Pipeline Hook
X-Gitlab-Token: <webhook_secret>
```

## Monitoring and Troubleshooting

### Check Webhook Status

View your repository connection to see webhook status:

```http
GET /api/v2/repositories/connections/{connection_id}
Authorization: Bearer <jwt_token>
```

**Response includes:**
- `webhook_status`: "active", "inactive", or "failed"
- `webhook_created_at`: When webhook was created
- `webhook_last_delivery_at`: Last successful webhook delivery
- `webhook_events`: Events being monitored

### Webhook Statuses

| Status | Description | Action |
|--------|-------------|--------|
| `active` | Webhook is working correctly | None needed |
| `inactive` | Repository disconnected or webhook deleted | Reconnect repository if needed |
| `failed` | Webhook creation failed | Check OAuth permissions and try again |

### Common Issues

#### Webhook Creation Fails

**Symptoms:**
- `webhook_status: "failed"` in API response
- Repository connected but not receiving events

**Causes:**
1. Insufficient OAuth permissions (need `admin:repo_hook` scope)
2. GitHub/GitLab API temporarily unavailable
3. Repository is archived or deleted

**Solutions:**
1. Re-authorize with correct OAuth scopes
2. Disconnect and reconnect the repository
3. Check repository settings on GitHub/GitLab

#### Webhook Signature Verification Fails

**Symptoms:**
- 401 Unauthorized responses from webhook endpoint
- No incidents created for failed workflows

**Causes:**
1. Webhook secret mismatch
2. Payload tampering (very rare)
3. Webhook misconfigured manually in GitHub/GitLab

**Solutions:**
1. Disconnect and reconnect repository to regenerate webhook
2. Don't modify webhooks manually in GitHub/GitLab settings
3. Check application logs for detailed error messages

#### Webhook Not Receiving Events

**Symptoms:**
- Workflows fail but no incidents created
- `webhook_last_delivery_at` is old or null

**Causes:**
1. Webhook was manually deleted from GitHub/GitLab
2. GitHub/GitLab webhook delivery failing
3. DevFlowFix API endpoint unreachable from GitHub/GitLab

**Solutions:**
1. Reconnect repository to recreate webhook
2. Check webhook delivery history in GitHub/GitLab settings
3. Verify `WEBHOOK_BASE_URL` configuration is publicly accessible

## Best Practices

### 1. Use Default Events

The default events (`workflow_run`, `pull_request`, `push`) cover most use cases. Only customize if you have specific requirements.

### 2. Monitor Webhook Health

Periodically check `webhook_last_delivery_at` to ensure webhooks are receiving events:

```bash
# Should update after each workflow run
GET /api/v2/repositories/connections/{connection_id}
```

### 3. Don't Modify Webhooks Manually

DevFlowFix manages webhooks automatically. Manual changes in GitHub/GitLab settings may cause synchronization issues.

### 4. Rotate Secrets Regularly

Disconnect and reconnect repositories periodically to rotate webhook secrets:

```bash
# Every 90 days
DELETE /api/v2/repositories/connections/{connection_id}
POST /api/v2/repositories/connect
```

### 5. Test Webhooks After Connection

Trigger a workflow run after connecting a repository to verify webhook is working:

```bash
# 1. Connect repository
POST /api/v2/repositories/connect

# 2. Trigger a workflow (push commit or manual trigger)

# 3. Check incidents were created
GET /api/v2/incidents?repository=owner/repo
```

## Configuration

### Environment Variables

```bash
# Webhook base URL (must be publicly accessible from GitHub/GitLab)
WEBHOOK_BASE_URL=https://api.devflowfix.com

# Encryption key for webhook secrets
OAUTH_TOKEN_ENCRYPTION_KEY=<fernet_key>

# GitHub OAuth (requires admin:repo_hook scope for webhooks)
GITHUB_OAUTH_CLIENT_ID=<client_id>
GITHUB_OAUTH_CLIENT_SECRET=<client_secret>

# GitLab OAuth
GITLAB_OAUTH_CLIENT_ID=<client_id>
GITLAB_OAUTH_CLIENT_SECRET=<client_secret>
```

### Required OAuth Scopes

**GitHub:**
- `repo` - Access repositories
- `admin:repo_hook` - Create/delete webhooks

**GitLab:**
- `api` - Full API access (includes webhook management)

## Architecture

### Webhook Flow Diagram

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   GitHub/   │         │  DevFlowFix │         │  Database   │
│   GitLab    │         │    API      │         │             │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                       │
       │  1. Workflow Fails    │                       │
       ├──────────────────────>│                       │
       │                       │                       │
       │                       │  2. Look up repo      │
       │                       ├──────────────────────>│
       │                       │<──────────────────────┤
       │                       │   RepositoryConnection│
       │                       │                       │
       │                       │  3. Verify signature  │
       │                       │   (decrypt secret)    │
       │                       │                       │
       │                       │  4. Create incident   │
       │                       ├──────────────────────>│
       │                       │                       │
       │  5. Return 200 OK     │                       │
       │<──────────────────────┤                       │
       │                       │                       │
```

### Database Schema

**repository_connections table:**
```sql
webhook_id              VARCHAR(100)     -- GitHub/GitLab webhook ID
webhook_url             VARCHAR(500)     -- Webhook endpoint URL
webhook_secret          VARCHAR(512)     -- Encrypted webhook secret
webhook_events          JSON             -- Subscribed events list
webhook_status          VARCHAR(50)      -- active/inactive/failed
webhook_created_at      TIMESTAMP        -- Creation timestamp
webhook_last_delivery_at TIMESTAMP       -- Last successful delivery
```

## FAQ

### Q: Do I need to configure webhooks manually?

**A:** No! DevFlowFix automatically creates and manages webhooks when you connect repositories.

### Q: Can I customize which events are monitored?

**A:** Yes, pass `webhook_events` when connecting a repository:

```json
{
  "repository_full_name": "owner/repo",
  "webhook_events": ["workflow_run"]
}
```

### Q: What happens if webhook creation fails?

**A:** The repository is still connected, but you won't receive real-time notifications. You can disconnect and reconnect to retry webhook creation.

### Q: Are webhook secrets secure?

**A:** Yes, webhook secrets are encrypted at rest using Fernet encryption and never exposed in API responses.

### Q: Can I see webhook delivery history?

**A:** Check `webhook_last_delivery_at` in the repository connection API. For detailed delivery history, check GitHub/GitLab webhook settings.

### Q: Do webhooks work with private repositories?

**A:** Yes, as long as you have the correct OAuth permissions for the private repository.

### Q: What if I delete the webhook manually in GitHub?

**A:** DevFlowFix will stop receiving events. Disconnect and reconnect the repository to recreate the webhook.

### Q: Can I use the same webhook for multiple repositories?

**A:** No, each repository connection has its own unique webhook with a unique secret.

### Q: How do I know if webhooks are working?

**A:** Check `webhook_last_delivery_at` - it should update after each workflow run. You should also see incidents created for failed workflows.

### Q: Can I disable webhooks temporarily?

**A:** Yes, use the repository connection update endpoint to disable monitoring:

```http
PATCH /api/v2/repositories/connections/{connection_id}
{
  "is_enabled": false
}
```

This keeps the webhook but stops processing events.

## Support

If you encounter webhook issues:

1. **Check API logs** for detailed error messages
2. **Verify OAuth scopes** include webhook permissions
3. **Test webhook delivery** in GitHub/GitLab settings
4. **Contact support** at support@devflowfix.com

## Related Documentation

- [Repository Management API](/docs/api/repositories.md)
- [OAuth Integration Guide](/docs/user-guide/oauth-setup.md)
- [Incident Management](/docs/user-guide/incidents.md)
- [Architecture Overview](/docs/architecture/automatic-webhook-management.md)
