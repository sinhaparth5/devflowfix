# V2 API Guide for Frontend

Quick reference for integrating DevFlowFix v2 APIs in your frontend application.

Base URL: `/api/v2`

## Authentication
All endpoints require JWT token in `Authorization: Bearer <token>` header (except OAuth callbacks).

---

## OAuth Integration

### GitHub OAuth

**Start OAuth Flow**
- `POST /v2/oauth/github/authorize`
- Returns: `authorization_url`, `state`
- Frontend: Redirect user to `authorization_url`

**Get Connection Status**
- `GET /v2/oauth/github/connection`
- Returns: Connection details or 404

**Disconnect**
- `DELETE /v2/oauth/github/disconnect`
- Revokes token and removes connection

### GitLab OAuth

**Start OAuth Flow**
- `POST /v2/oauth/gitlab/authorize`
- Returns: `authorization_url`, `state`

**Refresh Token**
- `POST /v2/oauth/gitlab/refresh`
- Use when token expires

**Get Connection / Disconnect**
- Same pattern as GitHub

### List All Connections
- `GET /v2/oauth/connections`
- Returns: All active OAuth connections

---

## Repository Management

### List Repositories

**GitHub Repos**
- `GET /v2/repositories/github?page=1&per_page=30&sort=updated&direction=desc`
- Returns: Repositories with connection status

**GitLab Projects**
- `GET /v2/repositories/gitlab?page=1&per_page=30`
- Returns: Projects with connection status

### Connect Repository

**Connect**
- `POST /v2/repositories/connect`
- Send: `{ repository_full_name, auto_pr_enabled, setup_webhook, webhook_events }`
- Auto-creates webhook if `setup_webhook: true`
- Returns: Connection details with webhook status

**Connect GitLab**
- `POST /v2/repositories/gitlab/connect`
- Same pattern as GitHub

### Manage Connections

**List Connections**
- `GET /v2/repositories/connections?include_disabled=false`
- Returns: All repository connections

**Get Single Connection**
- `GET /v2/repositories/connections/{connection_id}`

**Update Connection**
- `PATCH /v2/repositories/connections/{connection_id}`
- Send: `{ is_enabled, auto_pr_enabled }`

**Disconnect**
- `DELETE /v2/repositories/connections/{connection_id}?delete_webhook=true`
- Auto-deletes webhook from provider

### Statistics

**Repository Stats**
- `GET /v2/repositories/stats`
- Returns: Total repos, active/inactive count, webhook count

### Data Sync

**Sync Workflows**
- `POST /v2/repositories/{connection_id}/sync/workflows?limit=30&status_filter=completed`
- Fetches workflow runs from GitHub

**Sync PRs**
- `POST /v2/repositories/{connection_id}/sync/prs?state=all&limit=30`
- Fetches pull requests from GitHub

**Sync All**
- `POST /v2/repositories/{connection_id}/sync?sync_workflows=true&sync_prs=true`

---

## Workflow Management

### List Workflow Runs

**Get Runs**
- `GET /v2/workflows/runs?repository_connection_id=<id>&status_filter=completed&limit=50`
- Filters: `status_filter` (queued, in_progress, completed), `conclusion_filter` (success, failure)
- Returns: Workflow runs with statistics

**Get Single Run**
- `GET /v2/workflows/runs/{run_id}`

**Get Statistics**
- `GET /v2/workflows/stats?repository_connection_id=<id>`
- Returns: Total runs, failures, success rate, avg duration

### Workflow Actions

**Rerun Workflow**
- `POST /v2/workflows/runs/{run_id}/rerun`
- Send: `{ retry_failed_jobs: false }`
- Triggers GitHub workflow rerun

---

## Pull Request Management

### Create PR

**Create PR for Incident**
- `POST /v2/prs/create`
- Send: `{ incident_id, branch_name?, use_ai_analysis, auto_commit, draft_pr }`
- Auto-generates fix and creates PR
- Returns: PR number, URL, details

### Get PR Information

**Get PRs for Incident**
- `GET /v2/prs/incidents/{incident_id}`
- Returns: All PRs for incident with current status

**Get PR Status**
- `GET /v2/prs/{owner}/{repo}/{pr_number}`
- Returns: Detailed PR info (state, commits, reviews, etc.)

**Get PR Statistics**
- `GET /v2/prs/stats`
- Returns: Total PRs, merge rate, success rate

---

## Analytics & Dashboard

### Workflow Trends

**Get Trends**
- `GET /v2/analytics/workflows/trends?days=30&period=day&repository_connection_id=<id>`
- Returns: Time-series data for runs, failures, success rate

### Repository Health

**Get Health Metrics**
- `GET /v2/analytics/repositories/health?repository_connection_id=<id>`
- Returns: Health score (0-100), workflow stats, incidents

### Incident Trends

**Get Incident Trends**
- `GET /v2/analytics/incidents/trends?days=30&period=day`
- Returns: Incidents created/resolved over time

### System Health

**Get Overall Health**
- `GET /v2/analytics/system/health`
- Returns: System status, resource counts, alerts

**Dashboard Summary**
- `GET /v2/analytics/dashboard`
- Returns: Complete dashboard with all metrics

---

## Webhooks

**GitHub Webhook**
- `POST /v2/webhooks/github`
- Auto-configured when connecting repository
- Processes: workflow_run, pull_request, push events

**GitLab Webhook**
- `POST /v2/webhooks/gitlab`
- Processes: pipeline_events, merge_requests_events

---

## Common Patterns

### Initial Setup Flow
1. `POST /v2/oauth/github/authorize` → Get auth URL
2. User authorizes on GitHub
3. Callback redirects to frontend
4. `GET /v2/repositories/github` → List repos
5. `POST /v2/repositories/connect` → Connect repo (auto-creates webhook)

### Monitor Workflows
1. `GET /v2/workflows/runs` → List recent runs
2. `GET /v2/analytics/workflows/trends` → View trends
3. Webhooks auto-create incidents for failures

### Auto-Fix Flow
1. Webhook creates incident from failed workflow
2. `POST /v2/prs/create` → Create fix PR
3. `GET /v2/prs/incidents/{id}` → Track PR status
4. PR merged → Incident resolved

### Dashboard Display
1. `GET /v2/analytics/dashboard` → Get all metrics
2. `GET /v2/analytics/repositories/health` → Repo health cards
3. `GET /v2/workflows/stats` → Workflow metrics

---

## Error Handling

All endpoints return standard error format:
```
{ "detail": "error message" }
```

Common status codes:
- 200/201: Success
- 400: Bad request (validation error)
- 401: Unauthorized (missing/invalid token)
- 404: Resource not found
- 500: Server error

---

## Notes

- All timestamps in ISO 8601 UTC format
- Pagination uses `page` and `per_page` parameters
- OAuth callbacks redirect to frontend automatically
- Webhooks require secrets (auto-managed)
- GitLab tokens expire and need refresh
- GitHub tokens don't expire
