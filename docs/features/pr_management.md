# PR Management: Automated PR Creation & Tracking

> DevFlowFix can automatically create pull requests with fixes in external repositories using NVIDIA API analysis.

## Overview

PR Management enables:

1. **Automated PR Creation** - When DevFlowFix detects a CI/CD failure, it:
   - Analyzes the error using NVIDIA LLM
   - Generates a solution with code fixes
   - Automatically creates a PR in the source repository

2. **Multi-Repository Support** - Manage tokens for multiple external repos
   - Per-repository tokens (recommended for security)
   - Organization-level fallback tokens

3. **PR Tracking** - Track all created PRs from within DevFlowFix:
   - View PR status and details
   - Monitor merge/close status
   - Get statistics on PR success rates

4. **Complete Audit Trail** - Every PR creation is logged:
   - Creation attempts and failures
   - Link to incident
   - Solution details and confidence scores

## Architecture

```
External Repository          DevFlowFix                GitHub API
     ↓                            ↓                         ↓
Webhook (failure)  →  Event Processor  →  NVIDIA API  →  Token Manager
                            ↓                              ↓
                       Analyzer Service  →  GitHub Client  →  Creates PR
                            ↓
                       PR Creator Service
                            ↓
                    Database (PR Metadata)
                            ↓
                    PR Management API
```

## Setup Guide

### Step 1: Register GitHub Tokens

Register Personal Access Tokens for each repository where DevFlowFix should create PRs:

```bash
curl -X POST "http://localhost:8000/api/v1/pr-management/tokens/register" \
  -G \
  --data-urlencode "owner=myorg" \
  --data-urlencode "repo=backend-service" \
  --data-urlencode "token=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  --data-urlencode "description=Token for backend-service auto-fix PRs" \
  --data-urlencode "scopes=repo,workflow,contents" \
  --data-urlencode "created_by=admin"
```

**Required Token Scopes:**
- `repo` - Full access to repositories
- `workflow` - Modify workflows
- `contents` - Read and write repository contents

**Token Types:**
- **Per-Repository** (recommended): `owner=myorg`, `repo=backend-service`
- **Organization-Wide** (fallback): `owner=myorg`, `repo=null`

### Step 2: Configure Webhooks in External Repos

In each external repository, add a webhook to GitHub:

1. Go to **Settings → Webhooks → Add webhook**
2. Set **Payload URL**: `http://your-devflowfix-server:8000/api/v1/webhooks/github`
3. Select events:
   - `workflow_run` - Workflow failures
   - `push` - Code push events
4. Set **Content type**: `application/json`
5. Add **Secret** (if configured) in DevFlowFix

### Step 3: Enable Auto-PR Creation

PRs are created automatically when:

- ✅ Failure is detected via webhook
- ✅ AI confidence is high (default: ≥85%)
- ✅ Failure type is auto-fixable (lint, test, config errors)
- ✅ Solution includes code changes
- ✅ Repository token is registered

## API Reference

### Token Management

#### Register Token
```
POST /api/v1/pr-management/tokens/register

Query Parameters:
  owner: string (required)         - GitHub organization/user
  repo: string (optional)          - Repository name (null for org-wide)
  token: string (required)         - GitHub Personal Access Token
  description: string              - Human-readable description
  scopes: string                   - Comma-separated: repo,workflow,contents
  created_by: string               - Who created this (for audit)

Response:
{
  "success": true,
  "message": "Token registered for myorg/backend-service",
  "token": {
    "id": "token_...",
    "repository": "myorg/backend-service",
    "token_masked": "ghp_...",
    "scopes": "repo,workflow,contents",
    "created_at": "2025-12-13T10:30:00Z"
  }
}
```

#### List Tokens
```
GET /api/v1/pr-management/tokens

Query Parameters:
  owner: string (optional)         - Filter by owner
  active_only: boolean             - Only list active tokens (default: true)

Response:
{
  "success": true,
  "count": 3,
  "tokens": [
    {
      "id": "token_...",
      "repository": "myorg/backend-service",
      "token_masked": "ghp_...",
      "description": "Token for backend-service auto-fix PRs",
      "created_at": "2025-12-13T10:30:00Z",
      "is_active": true
    }
  ]
}
```

#### Deactivate Token
```
POST /api/v1/pr-management/tokens/{token_id}/deactivate

Response:
{
  "success": true,
  "message": "Token ... deactivated"
}
```

### PR Tracking

#### List PRs
```
GET /api/v1/pr-management/pulls

Query Parameters:
  incident_id: string (optional)   - Filter by incident
  repository: string (optional)    - Filter by repository
  status_filter: string (optional) - created|open|merged|closed|failed
  skip: integer (default: 0)       - Pagination offset
  limit: integer (default: 20)     - Results per page

Response:
{
  "success": true,
  "total": 42,
  "prs": [
    {
      "id": "pr_...",
      "incident_id": "inc_...",
      "pr_number": 123,
      "pr_url": "https://github.com/myorg/backend/pull/123",
      "repository": "myorg/backend-service",
      "title": "DevFlowFix: Test Failure",
      "branch": "devflowfix/auto-fix-test-failure-abc123d",
      "status": "merged",
      "failure_type": "test_failure",
      "confidence_score": 0.92,
      "files_changed": 2,
      "additions": 15,
      "deletions": 8,
      "created_at": "2025-12-13T10:35:00Z",
      "merged_at": "2025-12-13T11:45:00Z"
    }
  ]
}
```

#### Get PR Details
```
GET /api/v1/pr-management/pulls/{pr_id}

Response:
{
  "success": true,
  "pr": {
    "id": "pr_...",
    "incident_id": "inc_...",
    "pr_number": 123,
    "pr_url": "https://github.com/myorg/backend/pull/123",
    "repository": "myorg/backend-service",
    "title": "DevFlowFix: Test Failure",
    "description": "...",  // Full PR description
    "branch": "devflowfix/auto-fix-test-failure-abc123d",
    "base_branch": "main",
    "status": "merged",
    "failure_type": "test_failure",
    "root_cause": "Assert condition not met",
    "confidence_score": 0.92,
    "files_changed": 2,
    "additions": 15,
    "deletions": 8,
    "commits_count": 1,
    "review_comments_count": 2,
    "approved_by": "reviewer-username",
    "has_conflicts": false,
    "created_at": "2025-12-13T10:35:00Z",
    "updated_at": "2025-12-13T12:00:00Z",
    "merged_at": "2025-12-13T11:45:00Z",
    "metadata": {...}
  }
}
```

#### Update PR Status
```
POST /api/v1/pr-management/pulls/{pr_id}/update-status

Query Parameters:
  new_status: string (required)    - created|open|approved|merged|closed|failed
  metadata: object (optional)      - Additional metadata

Response:
{
  "success": true,
  "message": "PR #123 status updated to merged",
  "status": "merged"
}
```

### Statistics

#### Get PR Statistics
```
GET /api/v1/pr-management/stats

Response:
{
  "success": true,
  "statistics": {
    "total_prs": 42,
    "merged_count": 38,
    "merge_rate": 90.5,
    "avg_files_per_pr": 1.8,
    "total_additions": 284,
    "total_deletions": 156,
    "status_distribution": {
      "merged": 38,
      "open": 2,
      "closed": 2,
      "failed": 0
    }
  }
}
```

## Workflow Example

### 1. Repository Failure Occurs

External repo (myorg/backend-service) has a failing test:

```
Test Suite Failed
  ✗ test_user_auth.py::test_login_validation
    AssertionError: expected True but got False
```

### 2. Webhook Sent to DevFlowFix

```json
{
  "action": "completed",
  "workflow_run": {
    "name": "Tests",
    "conclusion": "failure",
    "repository": {
      "full_name": "myorg/backend-service"
    }
  }
}
```

### 3. DevFlowFix Analyzes

- Creates Incident
- Generates embedding
- Searches vector DB for similar incidents (RAG)
- Calls NVIDIA Llama 3.1 for analysis:
  - Root cause: "Test validation logic error"
  - Fix: Add missing assertion condition
  - Confidence: 92%

### 4. Solution Generated

NVIDIA API returns:

```json
{
  "code_changes": [
    {
      "file_path": "tests/test_user_auth.py",
      "current_code": "assert user.is_authenticated",
      "fixed_code": "assert user.is_authenticated and user.email_verified",
      "explanation": "Email verification check was missing"
    }
  ],
  "immediate_fix": {
    "description": "Add email verification check to login validation",
    "steps": ["Update assertion", "Run tests"],
    "estimated_time_minutes": 2,
    "risk_level": "low"
  }
}
```

### 5. PR Automatically Created

DevFlowFix:
1. Gets GitHub token for `myorg/backend-service`
2. Creates branch: `devflowfix/auto-fix-test-failure-inc12345678`
3. Commits fix: "fix: Add email verification check to login validation"
4. Creates PR with full explanation
5. Stores PR metadata in database

**Resulting PR:**
- Number: #445
- Title: "DevFlowFix: Test Failure"
- Branch: `devflowfix/auto-fix-test-failure-inc12345678`
- Status: `created` → `open` → (reviewer reviews) → `merged`

### 6. Track in DevFlowFix

View PR details:
```
GET /api/v1/pr-management/pulls/pr_xxxxx

Response: PR #445 details, status, metadata
```

## Security Considerations

### Token Encryption

Tokens are encrypted at rest if `DEVFLOWFIX_ENCRYPTION_KEY` is set:

```bash
export DEVFLOWFIX_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

### Token Scope Best Practices

- Use **repository-specific tokens** when possible
- Grant minimal required scopes: `repo`, `workflow`, `contents`
- Rotate tokens periodically
- Deactivate tokens when no longer needed
- Use separate tokens per repository/team

### Access Control

- Only authenticated API users can register/list tokens
- Token values are masked in API responses
- Full audit trail of token operations
- Deactivation is soft-delete (recoverable)

## Troubleshooting

### PR Creation Failed: "No GitHub token found"

**Solution:** Register a token for the repository:
```bash
curl -X POST "http://localhost:8000/api/v1/pr-management/tokens/register" \
  -G \
  --data-urlencode "owner=myorg" \
  --data-urlencode "repo=backend-service" \
  --data-urlencode "token=ghp_..." \
  --data-urlencode "scopes=repo,workflow,contents"
```

### PR Status Not Updating

**Solution:** Manually update via API:
```bash
curl -X POST "http://localhost:8000/api/v1/pr-management/pulls/{pr_id}/update-status" \
  -G --data-urlencode "new_status=merged"
```

### Low PR Merge Rate

**Possible Causes:**
- Confidence threshold too high (increase to allow more PRs)
- Failure types not in auto-fix list
- GitHub token permissions insufficient
- Manual review requirements

**Check logs:**
```
GET /api/v1/pr-management/stats  # View merge rate
```

## Configuration

### Environment Variables

```bash
# Encryption for stored tokens
export DEVFLOWFIX_ENCRYPTION_KEY="..."

# Auto-PR settings (in future versions)
export DEVFLOWFIX_MIN_PR_CONFIDENCE=0.85
export DEVFLOWFIX_AUTO_PR_ENABLED=true
```

### Database Migration

Create PR management tables:

```bash
# Run migrations (if using Alembic)
alembic upgrade head
```

## Examples

See [pr_management_setup.py](../examples/pr_management_setup.py) for:
- Complete setup script
- Token registration
- Webhook simulation
- PR listing and tracking
- Statistics viewing

Run it:
```bash
python examples/pr_management_setup.py
```

## Next Steps

1. ✅ Register GitHub tokens for external repos
2. ✅ Configure webhooks in GitHub
3. ✅ Monitor PR creation in real-time
4. ✅ Review and merge PRs
5. ✅ View statistics and success rates

---

For more details, see:
- [Architecture Overview](../architecture/overview.md)
- [Webhook Documentation](./webhook.md)
- [API Documentation](./api.md)
