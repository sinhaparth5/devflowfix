# GitHub/GitLab OAuth Integration - Implementation Plan

**Date:** 2025-12-30
**Status:** Planning Phase
**Goal:** Replace webhook-only approach with OAuth-based GitHub/GitLab integration for better repository access

---

## 📋 Table of Contents

1. [Current Architecture & Limitations](#current-architecture--limitations)
2. [Proposed Architecture](#proposed-architecture)
3. [Required Changes](#required-changes)
4. [Implementation Phases](#implementation-phases)
5. [Migration Strategy](#migration-strategy)
6. [Security Considerations](#security-considerations)
7. [Estimated Effort](#estimated-effort)

---

## 🔍 Current Architecture & Limitations

### How It Works Now

**Flow:**
```
GitHub Workflow Fails
    ↓
Webhook Event Sent
    ↓
DevFlowFix Receives Webhook
    ↓
Fetches Logs (using stored PAT token)
    ↓
Analyzes with LLM
    ↓
Creates PR (using user's PAT token)
```

### Current Limitations

1. **Limited GitHub Access**
   - ❌ Can only react to webhook events
   - ❌ Cannot proactively fetch repository information
   - ❌ Cannot list user's repositories
   - ❌ Cannot access private repos without manual PAT setup
   - ❌ No access to pull request details, comments, reviews
   - ❌ Cannot fetch workflow runs history

2. **Token Management Issues**
   - ❌ Users must manually provide Personal Access Tokens (PATs)
   - ❌ Tokens stored per-repository (cumbersome)
   - ❌ No token refresh mechanism
   - ❌ Security risk if tokens are compromised

3. **User Experience Problems**
   - ❌ Complex setup (webhook + secret + PAT token)
   - ❌ Requires manual configuration for each repository
   - ❌ No visibility into which repos are connected
   - ❌ Difficult to troubleshoot connection issues

4. **Missing Features**
   - ❌ Cannot fetch file contents from repository
   - ❌ Cannot read existing PRs or issues
   - ❌ Cannot analyze workflow history
   - ❌ Cannot determine changed files properly
   - ❌ Limited error context extraction

---

## 🎯 Proposed Architecture

### OAuth-Based Integration

**New Flow:**
```
User Connects GitHub Account (OAuth)
    ↓
DevFlowFix Gets OAuth Token with Repo Access
    ↓
User Selects Repositories to Monitor
    ↓
DevFlowFix Installs Webhooks Automatically
    ↓
--- On Failure Event ---
    ↓
Webhook Event Received
    ↓
Fetch Full Context via GitHub API:
  - Repository files
  - Workflow run details
  - Commit information
  - Changed files diff
    ↓
Analyze with LLM
    ↓
Create PR with Full Context
```

### Key Improvements

1. **Seamless OAuth Flow**
   - ✅ One-click "Connect GitHub" button
   - ✅ Standard OAuth 2.0 flow
   - ✅ Automatic token refresh
   - ✅ Granular permissions (only what's needed)

2. **Full GitHub Access**
   - ✅ List all user repositories
   - ✅ Access private repositories
   - ✅ Fetch file contents
   - ✅ Read PR details and comments
   - ✅ Access workflow run logs
   - ✅ Get commit diffs

3. **Automatic Setup**
   - ✅ Auto-install webhooks
   - ✅ Auto-configure webhook secrets
   - ✅ One token for all repos
   - ✅ Easy enable/disable per repository

4. **Better Error Context**
   - ✅ Fetch actual source files
   - ✅ Get complete commit diffs
   - ✅ Analyze changed files accurately
   - ✅ Access workflow YAML for context

---

## 🔧 Required Changes

### 1. Database Schema Changes

**New Tables Needed:**

```sql
-- OAuth connections table
CREATE TABLE oauth_connections (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(user_id),
    provider VARCHAR(20) NOT NULL,  -- 'github' or 'gitlab'
    provider_user_id VARCHAR(100),   -- GitHub/GitLab user ID
    provider_username VARCHAR(100),
    access_token TEXT NOT NULL,      -- Encrypted OAuth token
    refresh_token TEXT,               -- For token refresh
    token_expires_at TIMESTAMPTZ,
    scopes TEXT[],                    -- Granted permissions
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    UNIQUE(user_id, provider)
);

-- Repository connections table
CREATE TABLE repository_connections (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(user_id),
    oauth_connection_id VARCHAR(36) REFERENCES oauth_connections(id),
    provider VARCHAR(20) NOT NULL,
    repository_id VARCHAR(100),      -- GitHub repo ID
    repository_full_name VARCHAR(255), -- e.g., "owner/repo"
    repository_name VARCHAR(255),
    owner_name VARCHAR(255),
    is_private BOOLEAN,
    webhook_id VARCHAR(100),         -- GitHub webhook ID
    webhook_secret VARCHAR(255),
    is_enabled BOOLEAN DEFAULT TRUE,
    auto_pr_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_event_at TIMESTAMPTZ,

    UNIQUE(user_id, repository_full_name)
);

-- Workflow run tracking
CREATE TABLE workflow_runs (
    id VARCHAR(36) PRIMARY KEY,
    incident_id VARCHAR(36) REFERENCES incidents(incident_id),
    repository_connection_id VARCHAR(36) REFERENCES repository_connections(id),
    run_id VARCHAR(100),             -- GitHub workflow run ID
    workflow_name VARCHAR(255),
    status VARCHAR(50),
    conclusion VARCHAR(50),
    run_number INTEGER,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

**Modify Existing Tables:**

```sql
-- Add oauth_connection_id to incidents
ALTER TABLE incidents
ADD COLUMN oauth_connection_id VARCHAR(36) REFERENCES oauth_connections(id),
ADD COLUMN repository_connection_id VARCHAR(36) REFERENCES repository_connections(id);

-- Remove per-repo token columns (deprecated)
-- Keep for backward compatibility during migration
```

### 2. New API Endpoints

**OAuth Flow:**
```
POST   /api/v1/oauth/github/authorize        - Initiate GitHub OAuth
GET    /api/v1/oauth/github/callback         - OAuth callback handler
POST   /api/v1/oauth/gitlab/authorize        - Initiate GitLab OAuth
GET    /api/v1/oauth/gitlab/callback         - OAuth callback handler
GET    /api/v1/oauth/connections             - List user's OAuth connections
DELETE /api/v1/oauth/connections/{id}        - Disconnect OAuth
POST   /api/v1/oauth/connections/{id}/refresh - Manually refresh token
```

**Repository Management:**
```
GET    /api/v1/repositories                  - List available repositories
POST   /api/v1/repositories/{id}/connect     - Enable monitoring for repo
DELETE /api/v1/repositories/{id}/disconnect  - Disable monitoring
PATCH  /api/v1/repositories/{id}/settings    - Update repo settings
GET    /api/v1/repositories/{id}/status      - Get connection status
POST   /api/v1/repositories/{id}/test        - Test webhook connection
```

**GitHub/GitLab Integration:**
```
GET    /api/v1/github/repos/{owner}/{repo}/files       - List files
GET    /api/v1/github/repos/{owner}/{repo}/file/{path} - Get file content
GET    /api/v1/github/repos/{owner}/{repo}/workflows   - List workflows
GET    /api/v1/github/runs/{run_id}/logs               - Get workflow logs
GET    /api/v1/github/commits/{sha}/diff               - Get commit diff
```

### 3. New Services/Adapters

**OAuth Service:**
```python
app/services/oauth/
├── __init__.py
├── github_oauth.py      # GitHub OAuth handler
├── gitlab_oauth.py      # GitLab OAuth handler
├── token_manager.py     # Token refresh & storage
└── provider_base.py     # Base class for OAuth providers
```

**Repository Service:**
```python
app/services/repository/
├── __init__.py
├── repository_manager.py    # Repository CRUD operations
├── webhook_manager.py       # Auto webhook setup/teardown
└── sync_service.py          # Sync repos from GitHub/GitLab
```

**Enhanced GitHub Client:**
```python
app/adapters/external/github/
├── client.py                # Existing client
├── oauth_client.py          # OAuth-authenticated client
├── repository_client.py     # Repository operations
├── workflow_client.py       # Workflow operations
└── webhook_client.py        # Webhook management
```

### 4. Configuration Changes

**Environment Variables:**
```bash
# GitHub OAuth
GITHUB_OAUTH_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_OAUTH_CLIENT_SECRET=your_github_oauth_app_secret
GITHUB_OAUTH_REDIRECT_URI=https://yourapp.com/api/v1/oauth/github/callback

# GitLab OAuth
GITLAB_OAUTH_CLIENT_ID=your_gitlab_oauth_app_client_id
GITLAB_OAUTH_CLIENT_SECRET=your_gitlab_oauth_app_secret
GITLAB_OAUTH_REDIRECT_URI=https://yourapp.com/api/v1/oauth/gitlab/callback

# OAuth Scopes
GITHUB_OAUTH_SCOPES=repo,read:user,admin:repo_hook
GITLAB_OAUTH_SCOPES=api,read_user,read_repository

# Token Encryption
OAUTH_TOKEN_ENCRYPTION_KEY=your_encryption_key_for_tokens
```

### 5. Frontend Changes

**New Pages/Components:**

1. **OAuth Connection Page** (`/settings/integrations`)
   - Connect GitHub button
   - Connect GitLab button
   - Show connected accounts
   - Disconnect option

2. **Repository Management Page** (`/repositories`)
   - List all accessible repositories
   - Enable/disable per repository
   - Configure auto-PR settings
   - View connection status
   - Test webhook button

3. **Repository Details Page** (`/repositories/{id}`)
   - Recent incidents for this repo
   - Workflow runs history
   - Created PRs
   - Settings panel

4. **OAuth Callback Handler**
   - Handle OAuth redirect
   - Show success/error messages
   - Redirect to repository selection

---

## 📅 Implementation Phases

### Phase 1: OAuth Foundation (Week 1)
**Goal:** Basic OAuth flow working

- [ ] Create GitHub OAuth App
- [ ] Create GitLab OAuth App
- [ ] Implement database schema changes (new tables)
- [ ] Create OAuth service base classes
- [ ] Implement GitHub OAuth flow
- [ ] Implement token encryption/decryption
- [ ] Create OAuth API endpoints
- [ ] Add basic frontend OAuth button

**Deliverables:**
- Users can connect GitHub account
- OAuth token stored securely
- Basic "Connected" status shown

### Phase 2: Repository Management (Week 2)
**Goal:** Repository selection and webhook automation

- [ ] Implement repository sync from GitHub
- [ ] Create repository management API
- [ ] Implement automatic webhook installation
- [ ] Create repository list UI
- [ ] Add enable/disable toggle per repo
- [ ] Implement webhook secret auto-generation

**Deliverables:**
- Users can see all their repos
- Enable/disable monitoring per repo
- Webhooks auto-installed

### Phase 3: Enhanced GitHub Integration (Week 3)
**Goal:** Fetch full context from GitHub

- [ ] Implement OAuth-based GitHub client
- [ ] Add file content fetching
- [ ] Add commit diff fetching
- [ ] Add workflow run details fetching
- [ ] Update event processor to use OAuth client
- [ ] Enhance error context extraction

**Deliverables:**
- LLM gets actual file contents
- Better error context
- More accurate code fixes

### Phase 4: Migration & Deprecation (Week 4)
**Goal:** Migrate existing users

- [ ] Create migration script for PAT → OAuth
- [ ] Add backward compatibility layer
- [ ] Update documentation
- [ ] Create user migration guide
- [ ] Deprecate PAT-based flow (with warning)

**Deliverables:**
- Existing users migrated
- Both flows work (for transition)
- Documentation updated

### Phase 5: GitLab Support (Week 5)
**Goal:** Add GitLab OAuth

- [ ] Implement GitLab OAuth flow
- [ ] Implement GitLab client
- [ ] Add GitLab webhook support
- [ ] Update UI for GitLab
- [ ] Test end-to-end

**Deliverables:**
- GitLab OAuth working
- Same features as GitHub

### Phase 6: Polish & Advanced Features (Week 6+)
**Goal:** Enhanced user experience

- [ ] Add repository search/filter
- [ ] Add batch enable/disable
- [ ] Add webhook health checks
- [ ] Add token refresh UI indicator
- [ ] Add repository statistics
- [ ] Add webhook event history

**Deliverables:**
- Polished UI
- Advanced management features
- Production-ready

---

## 🔄 Migration Strategy

### Backward Compatibility

**During Transition Period (3-6 months):**

1. **Dual Mode Support**
   - Both PAT tokens and OAuth tokens work
   - Webhook handler checks both auth methods
   - New users encouraged to use OAuth
   - Existing users get migration banner

2. **Data Migration**
   ```python
   # Migration script
   - For each user with github_access_token (PAT):
     - Create oauth_connection record
     - Mark as "migrated_from_pat"
     - Keep PAT as fallback

   - For each repository in github_token_manager:
     - Create repository_connection record
     - Link to user's OAuth connection
     - Preserve webhook settings
   ```

3. **Deprecation Timeline**
   - Month 1-2: Both methods work, show migration notice
   - Month 3-4: OAuth recommended, PAT deprecated warning
   - Month 5-6: PAT-only users get email reminders
   - Month 7+: PAT support removed (with grace period)

### Rollout Strategy

1. **Beta Testing** (Week 1-2)
   - Enable for internal users only
   - Test all OAuth flows
   - Collect feedback

2. **Gradual Rollout** (Week 3-4)
   - Enable for 10% of users
   - Monitor error rates
   - Fix issues quickly

3. **Full Rollout** (Week 5+)
   - Enable for all new users
   - Migrate existing users progressively
   - Monitor metrics

---

## 🔒 Security Considerations

### Token Storage

1. **Encryption at Rest**
   ```python
   from cryptography.fernet import Fernet

   # Encrypt OAuth tokens before storing
   cipher_suite = Fernet(settings.OAUTH_TOKEN_ENCRYPTION_KEY)
   encrypted_token = cipher_suite.encrypt(access_token.encode())
   ```

2. **Token Scope Minimization**
   - Only request necessary scopes
   - GitHub: `repo`, `read:user`, `admin:repo_hook`
   - Avoid `admin:org`, `delete_repo`, etc.

3. **Token Refresh**
   - Implement automatic refresh before expiry
   - Handle refresh token rotation
   - Invalidate expired tokens

### OAuth Security

1. **State Parameter**
   - Use CSRF state parameter in OAuth flow
   - Validate state on callback
   - Prevent replay attacks

2. **HTTPS Only**
   - All OAuth endpoints HTTPS only
   - Secure cookie flags
   - HSTS headers

3. **Webhook Verification**
   - Continue HMAC signature verification
   - Rate limiting on webhook endpoints
   - IP whitelist (optional)

---

## 📊 Estimated Effort

### Development Time

| Phase | Tasks | Developer Time | Calendar Time |
|-------|-------|----------------|---------------|
| Phase 1: OAuth Foundation | 15 tasks | 40 hours | 1 week |
| Phase 2: Repository Management | 12 tasks | 35 hours | 1 week |
| Phase 3: Enhanced Integration | 10 tasks | 30 hours | 1 week |
| Phase 4: Migration | 8 tasks | 20 hours | 1 week |
| Phase 5: GitLab Support | 10 tasks | 25 hours | 1 week |
| Phase 6: Polish | 8 tasks | 20 hours | 1-2 weeks |
| **Total** | **63 tasks** | **170 hours** | **6-7 weeks** |

### Code Impact Assessment

| Component | Impact Level | Files to Modify | New Files | Effort |
|-----------|--------------|-----------------|-----------|--------|
| Database Schema | HIGH | 1 migration | 0 | 4h |
| OAuth Services | HIGH | 0 | 8 new | 30h |
| Repository Management | HIGH | 0 | 6 new | 25h |
| GitHub Client | MEDIUM | 2 existing | 4 new | 20h |
| API Endpoints | HIGH | 0 | 10 new | 25h |
| Webhook Handler | MEDIUM | 1 existing | 0 | 8h |
| Event Processor | MEDIUM | 1 existing | 0 | 6h |
| PR Creator | LOW | 1 existing | 0 | 4h |
| Frontend | HIGH | N/A | 15 new | 40h |
| Tests | MEDIUM | 0 | 20 new | 20h |

**Total Estimated Files:**
- Modified: ~8 files
- Created: ~63 new files
- Tests: ~20 new test files

---

## ✅ Success Criteria

### Phase 1 Complete When:
- [ ] User can click "Connect GitHub"
- [ ] OAuth flow completes successfully
- [ ] Token stored encrypted in database
- [ ] User sees "Connected" status

### Phase 2 Complete When:
- [ ] User sees list of all repositories
- [ ] Can toggle monitoring per repository
- [ ] Webhook auto-installed on enable
- [ ] Webhook auto-removed on disable

### Phase 3 Complete When:
- [ ] Incident processing uses OAuth token
- [ ] File contents fetched from GitHub
- [ ] Commit diffs retrieved
- [ ] Code changes more accurate

### Full Project Complete When:
- [ ] All 6 phases delivered
- [ ] 95%+ users migrated to OAuth
- [ ] PAT flow deprecated
- [ ] Documentation complete
- [ ] No critical bugs

---

## 🎯 Next Steps

### Immediate Actions:

1. **Create GitHub OAuth App**
   - Go to GitHub Settings > Developer Settings > OAuth Apps
   - Register new OAuth application
   - Note Client ID and Secret

2. **Create GitLab OAuth App**
   - Go to GitLab Settings > Applications
   - Register new application
   - Note Application ID and Secret

3. **Database Migration**
   - Create Alembic migration for new tables
   - Test migration on dev environment
   - Prepare rollback script

4. **Start Phase 1**
   - Set up development environment
   - Create feature branch: `feature/github-oauth-integration`
   - Begin implementing OAuth service

### Questions to Resolve:

- [ ] Should we support GitHub Enterprise?
- [ ] Support self-hosted GitLab instances?
- [ ] Allow multiple GitHub accounts per user?
- [ ] Implement organization-level connections?
- [ ] Support GitHub App instead of OAuth App?

---

## 📚 References

- [GitHub OAuth Documentation](https://docs.github.com/en/developers/apps/building-oauth-apps)
- [GitLab OAuth Documentation](https://docs.gitlab.com/ee/api/oauth2.html)
- [OAuth 2.0 RFC](https://datatracker.ietf.org/doc/html/rfc6749)
- [GitHub REST API](https://docs.github.com/en/rest)
- [GitLab API](https://docs.gitlab.com/ee/api/)

---

**Document Version:** 1.0
**Last Updated:** 2025-12-30
**Author:** DevFlowFix Team
