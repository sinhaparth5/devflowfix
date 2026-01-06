# Automatic Fix Flow - Complete Guide

## Overview

DevFlowFix now **automatically** creates AI-powered fix PRs when workflows fail. No manual intervention needed!

## Complete Automatic Flow

```
1. Developer pushes code
         ↓
2. GitHub Actions workflow runs
         ↓
3. Workflow FAILS ❌
         ↓
4. GitHub sends webhook to DevFlowFix
         ↓
5. DevFlowFix receives webhook
         ↓
6. Creates Incident in database
         ↓
7. Checks if auto_pr_enabled = true ✓
         ↓
8. AUTOMATIC PR CREATION BEGINS
         ↓
9. Fetch workflow logs from GitHub
         ↓
10. Parse logs → Find errors:
    - File: src/components/Button.tsx
    - Line: 42
    - Error: 'React' is not defined
         ↓
11. Fetch file content from GitHub
         ↓
12. Send to AI (LLM):
    - Error details
    - File content
    - Context
         ↓
13. AI generates fix:
    - Add import React from 'react'
    - Fix line 42
         ↓
14. Create branch: devflowfix/fix-INC-abc123
         ↓
15. Commit fixes to branch
         ↓
16. Create Pull Request automatically 🎉
         ↓
17. PR includes:
    - Fixed code
    - AI analysis
    - Error details
    - Testing checklist
         ↓
18. Developer reviews & merges ✓
```

## Setup Instructions

### 1. Connect Repository

```bash
POST /api/v2/repositories/connect
Authorization: Bearer <jwt_token>

{
  "repository_full_name": "owner/repo",
  "auto_pr_enabled": true,        # ← ENABLE AUTOMATIC PR CREATION
  "setup_webhook": true,
  "webhook_events": ["workflow_run", "pull_request", "push"]
}
```

**Key Setting:**
- `auto_pr_enabled: true` - This enables automatic PR creation on failures

### 2. Webhook Configuration

When you connect a repository, DevFlowFix automatically:
- ✅ Creates webhook in GitHub
- ✅ Configures webhook URL
- ✅ Sets webhook secret
- ✅ Subscribes to workflow_run events

**Webhook URL:** `https://your-domain.com/api/v2/webhooks/github`

**Events Monitored:**
- `workflow_run` - Detects workflow failures
- `pull_request` - Tracks PR status
- `push` - Monitors code changes

### 3. OAuth Permissions

Ensure your GitHub OAuth has these scopes:
- `repo` - Full repository access
- `workflow` - Workflow management
- `admin:repo_hook` - Webhook management

## How Auto-PR Works

### Step 1: Workflow Fails

GitHub Actions workflow fails with errors like:

```
❌ ESLint Error
src/components/Button.tsx:42:5 error 'React' is not defined

❌ TypeScript Error
src/api/user.ts:15:3 error Type 'string' is not assignable to type 'number'

❌ Build Error
Module not found: Error: Can't resolve './config'
```

### Step 2: Webhook Triggers

GitHub immediately sends webhook to DevFlowFix:

```json
{
  "action": "completed",
  "workflow_run": {
    "id": 123456789,
    "conclusion": "failure",
    "name": "CI Build",
    "html_url": "https://github.com/owner/repo/actions/runs/123456789"
  }
}
```

### Step 3: Incident Created

DevFlowFix creates incident record:

```python
{
  "incident_id": "INC-A1B2C3D4",
  "repository": "owner/repo",
  "workflow_name": "CI Build",
  "branch": "main",
  "commit_sha": "abc123",
  "status": "open",
  "severity": "high",
  "metadata": {
    "run_id": "123456789",
    "run_url": "...",
    "logs_url": "..."
  }
}
```

### Step 4: Auto-PR Triggered

If `repo_conn.auto_pr_enabled == true`:

```python
# Automatically triggered by webhook handler
1. Initialize AIFixGenerator
2. Generate fixes for incident
3. Create PR with fixes
```

### Step 5: AI Analyzes & Fixes

**Fetch Logs:**
```
GET https://api.github.com/repos/owner/repo/actions/jobs/{job_id}/logs
```

**Parse Errors:**
```python
[
  ErrorBlock(
    file_path="src/components/Button.tsx",
    line_number=42,
    error_type="lint_error",
    error_message="'React' is not defined"
  )
]
```

**Fetch File:**
```
GET https://api.github.com/repos/owner/repo/contents/src/components/Button.tsx
```

**AI Generates Fix:**
```python
{
  "code_changes": [
    {
      "line_number": 1,
      "fixed_line": "import React from 'react';",
      "explanation": "Added missing React import"
    }
  ]
}
```

### Step 6: PR Created

**Branch:** `devflowfix/fix-INC-A1B2C3D4`

**Commits:**
```
fix: Add missing React import
fix: Correct type mismatch in user.ts
```

**PR Description:**
```markdown
## 🤖 Automated Fix by DevFlowFix

### Incident Details
- **Incident ID:** INC-A1B2C3D4
- **Workflow:** CI Build
- **Branch:** main
- **Commit:** abc123

### AI Analysis
**Errors Detected:** 2
**Files Fixed:** 2

#### Issues Found:
- **lint_error**: 1 occurrence(s)
- **type_error**: 1 occurrence(s)

#### Files Modified:
- `src/components/Button.tsx` - Added missing React import
- `src/api/user.ts` - Fixed type mismatch

### Testing
- [ ] Verify workflow runs successfully
- [ ] Review code changes
- [ ] Merge if tests pass
```

## Configuration Options

### Repository Connection Settings

```python
{
  "auto_pr_enabled": true,      # Enable/disable automatic PR creation
  "is_enabled": true,           # Enable/disable repository monitoring
  "webhook_url": "...",         # Webhook endpoint
  "default_branch": "main",     # Base branch for PRs
}
```

### Enable/Disable Auto-PR

**Enable:**
```bash
PATCH /api/v2/repositories/connections/{connection_id}
{
  "auto_pr_enabled": true
}
```

**Disable:**
```bash
PATCH /api/v2/repositories/connections/{connection_id}
{
  "auto_pr_enabled": false
}
```

## Manual PR Creation (Optional)

If you disabled auto-PR or want to create additional PRs:

```bash
POST /api/v2/prs/create
{
  "incident_id": "INC-A1B2C3D4",
  "use_ai_analysis": true,
  "draft_pr": false
}
```

## Monitoring Auto-PRs

### Check PR Status

```bash
GET /api/v2/prs/incidents/{incident_id}
```

**Response:**
```json
{
  "incident_id": "INC-A1B2C3D4",
  "prs": [
    {
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo/pull/42",
      "state": "open",
      "branch_name": "devflowfix/fix-INC-A1B2C3D4",
      "created_at": "2025-01-06T10:30:00Z"
    }
  ]
}
```

### View Statistics

```bash
GET /api/v2/prs/stats
```

**Response:**
```json
{
  "total_prs_created": 25,
  "merged_prs": 18,
  "open_prs": 5,
  "merge_rate": 72.0,
  "incidents_auto_fixed": 18
}
```

## Webhook Response Format

When auto-PR is created, webhook returns:

```json
{
  "status": "ok",
  "action": "incident_created",
  "incident_id": "INC-A1B2C3D4",
  "workflow_run_id": "123456789",
  "auto_pr_created": true,
  "pr_number": 42,
  "pr_url": "https://github.com/owner/repo/pull/42"
}
```

## Error Handling

### If Auto-PR Fails

The webhook still succeeds and creates the incident, but logs the error:

```python
logger.error(
    "auto_pr_creation_error",
    incident_id=incident_id,
    error=str(e)
)
```

**Response:**
```json
{
  "status": "ok",
  "action": "incident_created",
  "incident_id": "INC-A1B2C3D4",
  "auto_pr_created": false,
  "pr_number": null,
  "pr_url": null
}
```

You can manually create PR later using the API.

### Common Issues

**1. No OAuth Token**
- Error: "No GitHub OAuth connection found"
- Fix: Connect GitHub OAuth first

**2. No Workflow Logs**
- Error: "No errors found in workflow logs"
- Fix: Ensure workflow has detailed error logs

**3. Permission Issues**
- Error: "403 Forbidden"
- Fix: Check OAuth scopes include `repo`

## Best Practices

### 1. Enable Auto-PR for Specific Repos

Only enable for repos where you want automatic fixes:

```python
# Production repos with strict review
auto_pr_enabled = False

# Development/staging repos
auto_pr_enabled = True
```

### 2. Review Before Merging

Always review auto-generated PRs:
- ✅ Check the fix makes sense
- ✅ Run tests
- ✅ Verify no breaking changes

### 3. Monitor Statistics

Track auto-PR success rate:
```bash
GET /api/v2/prs/stats
```

Aim for:
- Merge rate > 70%
- Low false positive rate

### 4. Use Draft PRs (Optional)

Create draft PRs for extra safety:

```python
# In webhook handler, modify:
result = await pr_creator.create_pr_for_incident(
    draft=True,  # ← Create as draft
    ...
)
```

## Complete Example

### 1. Setup

```bash
# Connect repository with auto-PR enabled
POST /api/v2/repositories/connect
{
  "repository_full_name": "myorg/myapp",
  "auto_pr_enabled": true,
  "setup_webhook": true
}
```

### 2. Development

```bash
# Developer pushes code
git push origin main
```

### 3. Workflow Fails

```
❌ CI Build Failed
   - ESLint: 2 errors
   - TypeScript: 1 error
```

### 4. Automatic Fix

```
⏳ DevFlowFix analyzing...
✅ Errors identified
✅ AI generating fixes
✅ PR created: #42
```

### 5. Review & Merge

```
👀 Review PR #42
✅ Tests pass
✅ Code looks good
🎉 Merge PR
```

### 6. Workflow Succeeds

```
✅ CI Build Passed
   All tests green!
```

## Summary

With automatic PR creation:

1. **Zero manual intervention** - PRs created automatically
2. **Fast response** - Fixes generated within seconds
3. **AI-powered** - Intelligent error analysis
4. **Safe** - Always requires review before merge
5. **Configurable** - Enable/disable per repository

The complete flow from failure to fix happens **automatically**! 🚀
