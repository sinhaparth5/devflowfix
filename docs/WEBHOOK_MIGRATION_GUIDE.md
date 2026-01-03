# Webhook Migration Guide: V1 to V2

## Problem

If you're seeing this error when webhooks are received:
```json
{"detail":"Missing X-Hub-Signature-256 header. Configure webhook secret in GitHub repository settings."}
```

This means your webhooks are either:
1. Using the old v1 endpoint (`/api/v1/webhook/...`)
2. Missing webhook secrets in the database
3. Not configured with secrets in GitHub

## Why This Happens

### V1 vs V2 Endpoints

**V1 Endpoint (Old):**
- URL: `https://api.devflowfix.com/api/v1/webhook/github/{user_id}`
- User-specific endpoints
- Manual webhook configuration required
- Secrets stored differently

**V2 Endpoint (New):**
- URL: `https://api.devflowfix.com/api/v2/webhooks/github`
- Universal endpoint for all users
- Automatic webhook management
- Encrypted secrets in database
- Better data isolation

### Migration Needed If:

- ✗ Repositories were connected before v2 webhook feature
- ✗ Webhooks were manually created in GitHub
- ✗ Webhook URL contains `/api/v1/webhook/`
- ✗ Missing `webhook_secret` in database

## Quick Fix

### Option 1: Reconnect Repository (Recommended)

This is the simplest solution:

1. **Disconnect the repository:**
   ```bash
   curl -X DELETE \
     "https://api.devflowfix.com/api/v2/repositories/connections/{connection_id}?delete_webhook=true" \
     -H "Authorization: Bearer {your_jwt_token}"
   ```

2. **Reconnect the repository:**
   ```bash
   curl -X POST \
     "https://api.devflowfix.com/api/v2/repositories/connect" \
     -H "Authorization: Bearer {your_jwt_token}" \
     -H "Content-Type: application/json" \
     -d '{
       "repository_full_name": "owner/repo",
       "setup_webhook": true
     }'
   ```

This will:
- ✓ Delete the old v1 webhook from GitHub
- ✓ Create a new v2 webhook with proper secret
- ✓ Update database with encrypted secret
- ✓ Configure webhook to use `/api/v2/webhooks/github`

### Option 2: Run Migration Script

For multiple repositories, use the migration script:

```bash
# 1. Check current webhook status
python scripts/check_webhook_status.py

# 2. Review the output and identified issues

# 3. Run migration script
python scripts/migrate_webhooks_to_v2.py

# 4. Verify migration
python scripts/check_webhook_status.py
```

## Detailed Migration Steps

### Step 1: Check Current Status

```bash
python scripts/check_webhook_status.py
```

**Expected output:**
```
================================================================================
WEBHOOK CONFIGURATION STATUS
================================================================================

Total active repositories: 5
Repositories with webhooks: 3
Repositories without webhooks: 2

WEBHOOK ENDPOINTS:
  V1 endpoints (/api/v1/webhook/): 2  ⚠️
  V2 endpoints (/api/v2/webhooks/): 1

WEBHOOK CONFIGURATION:
  Missing secrets: 1  ⚠️
  Inactive webhooks: 0

================================================================================
ISSUES DETECTED:
================================================================================
  ⚠️  2 webhooks using v1 endpoints (should migrate to v2)
  ⚠️  1 webhooks missing secrets

To fix these issues, run:
  python scripts/migrate_webhooks_to_v2.py
```

### Step 2: Run Migration

```bash
python scripts/migrate_webhooks_to_v2.py
```

**What the script does:**
1. Finds all repositories with webhooks
2. Identifies v1 endpoints and missing secrets
3. For each problematic webhook:
   - Deletes the old webhook from GitHub/GitLab
   - Creates a new v2 webhook with:
     - Universal endpoint URL
     - Generated webhook secret
     - Encrypted secret storage
   - Updates database with new configuration
4. Provides migration summary

**Expected output:**
```
Starting webhook migration to v2...
This will update webhooks to use /api/v2/webhooks/{provider} endpoints
and ensure all webhooks have proper secrets configured.

Do you want to continue? (yes/no): yes

processing_repository repository=owner/repo1 webhook_id=12345
v1_endpoint_detected repository=owner/repo1 current_url=/api/v1/webhook/github/user123
webhook_migrated_to_v2 repository=owner/repo1 new_webhook_id=67890

processing_repository repository=owner/repo2 webhook_id=54321
webhook_already_v2 repository=owner/repo2

=== Migration Summary ===
Total repositories: 3
V1 endpoints found: 1
Missing secrets: 1
Successfully updated: 2
Failed: 0
Skipped (already v2): 1
=========================

Migration completed!
```

### Step 3: Verify Migration

```bash
python scripts/check_webhook_status.py
```

All webhooks should now show:
- Endpoint: `v2 ✓`
- Secret: `✓`
- Status: `active ✓`

### Step 4: Test Webhook

Trigger a workflow in GitHub and verify:

1. **Webhook delivery in GitHub:**
   - Go to: `https://github.com/owner/repo/settings/hooks`
   - Click on the webhook
   - Check "Recent Deliveries"
   - Should see successful deliveries with 200 status

2. **Incident creation in DevFlowFix:**
   ```bash
   curl "https://api.devflowfix.com/api/v2/incidents?repository=owner/repo" \
     -H "Authorization: Bearer {your_jwt_token}"
   ```
   - Should see incidents created from webhook events

3. **Check logs:**
   ```bash
   # Application logs should show:
   github_webhook_received event_type=workflow_run delivery_id=...
   incident_created_from_webhook incident_id=INC-... repository=owner/repo
   ```

## Troubleshooting

### Issue: "Missing X-Hub-Signature-256 header"

**Cause:** Webhook created without secret in GitHub

**Fix:**
```bash
# 1. Check if webhook has secret in GitHub
# Go to: github.com/{owner}/{repo}/settings/hooks
# Click webhook → Edit → Check if "Secret" field is filled

# 2. If empty, reconnect repository:
python scripts/migrate_webhooks_to_v2.py
```

### Issue: "Webhook secret not found. Please reconnect the repository."

**Cause:** `webhook_secret` is NULL in database

**Fix:**
```bash
# Reconnect repository to generate and store secret
curl -X DELETE \
  "https://api.devflowfix.com/api/v2/repositories/connections/{id}?delete_webhook=true" \
  -H "Authorization: Bearer {token}"

curl -X POST \
  "https://api.devflowfix.com/api/v2/repositories/connect" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"repository_full_name": "owner/repo", "setup_webhook": true}'
```

### Issue: "Failed to decrypt webhook secret"

**Cause:** Encryption key changed or secret corrupted

**Fix:**
```bash
# 1. Check encryption key is set correctly
echo $OAUTH_TOKEN_ENCRYPTION_KEY

# 2. If key is correct but secret still corrupted, reconnect:
python scripts/migrate_webhooks_to_v2.py
```

### Issue: Webhooks still going to v1 endpoint

**Cause:** Old webhook not deleted from GitHub

**Fix:**
```bash
# Manually delete webhook in GitHub:
# 1. Go to: github.com/{owner}/{repo}/settings/hooks
# 2. Find webhook with URL containing /api/v1/webhook/
# 3. Click "Delete"

# Then create new webhook:
curl -X POST \
  "https://api.devflowfix.com/api/v2/repositories/connect" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"repository_full_name": "owner/repo", "setup_webhook": true}'
```

### Issue: Migration script fails with "No GitHub OAuth connection"

**Cause:** User hasn't connected GitHub OAuth

**Fix:**
```bash
# User must connect GitHub OAuth first:
# 1. Go to: https://devflowfix.com/settings/integrations
# 2. Click "Connect GitHub"
# 3. Authorize the app
# 4. Then retry migration
```

## Manual Verification Checklist

After migration, verify these points:

### GitHub Webhook Configuration

1. Go to `https://github.com/{owner}/{repo}/settings/hooks`
2. Verify:
   - ✓ Payload URL: `https://api.devflowfix.com/api/v2/webhooks/github`
   - ✓ Content type: `application/json`
   - ✓ Secret: `(set - not visible)`
   - ✓ SSL verification: Enabled
   - ✓ Events: Check only specific events
     - ✓ Workflow runs
     - ✓ Pull requests
     - ✓ Pushes
   - ✓ Active: Checked

### Database Verification

```sql
-- Check webhook configuration
SELECT
    repository_full_name,
    webhook_url,
    webhook_status,
    webhook_secret IS NOT NULL as has_secret,
    webhook_created_at,
    webhook_last_delivery_at
FROM repository_connections
WHERE is_enabled = true
  AND webhook_id IS NOT NULL;

-- Should show:
-- webhook_url: https://api.devflowfix.com/api/v2/webhooks/github
-- webhook_status: active
-- has_secret: true
-- webhook_last_delivery_at: (recent timestamp after test)
```

### API Verification

```bash
# Get repository connection status
curl "https://api.devflowfix.com/api/v2/repositories/connections/{id}" \
  -H "Authorization: Bearer {token}" | jq

# Should show:
# {
#   "webhook_url": "https://api.devflowfix.com/api/v2/webhooks/github",
#   "webhook_status": "active",
#   "webhook_events": ["workflow_run", "pull_request", "push"],
#   "webhook_created_at": "2025-01-02T10:00:00Z",
#   "webhook_last_delivery_at": "2025-01-02T11:30:00Z"
# }
```

## Prevention

To avoid this issue for new repositories:

1. **Always use the connect API:**
   ```bash
   POST /api/v2/repositories/connect
   {
     "repository_full_name": "owner/repo",
     "setup_webhook": true  // ← Always set to true
   }
   ```

2. **Never manually create webhooks in GitHub** - let DevFlowFix manage them

3. **Use environment variable:**
   ```bash
   WEBHOOK_BASE_URL=https://api.devflowfix.com
   ```

4. **Monitor webhook health:**
   ```bash
   # Run weekly
   python scripts/check_webhook_status.py
   ```

## FAQ

### Q: Will migration delete my workflow history?

**A:** No, only the webhook configuration changes. All incidents, workflow runs, and historical data remain intact.

### Q: Do I need to stop the application during migration?

**A:** No, migration can run while the application is serving traffic. The script gracefully handles concurrent requests.

### Q: What if migration fails for some repositories?

**A:** The script continues with other repositories and reports failures at the end. You can manually fix failed repositories and re-run.

### Q: Can I rollback if something goes wrong?

**A:** Yes, the old webhook still exists in GitHub until explicitly deleted. If migration fails, the old webhook continues working (though with v1 endpoint).

### Q: How long does migration take?

**A:** ~2 seconds per repository (GitHub API call + database update). For 10 repositories: ~20 seconds.

## Support

If you encounter issues during migration:

1. **Check logs:**
   ```bash
   tail -f logs/application.log | grep webhook
   ```

2. **Run diagnostic script:**
   ```bash
   python scripts/check_webhook_status.py
   ```

3. **Contact support:**
   - Email: support@devflowfix.com
   - Include: Repository name, error message, migration script output

4. **File issue:**
   - GitHub: https://github.com/devflowfix/devflowfix/issues
   - Include: Logs, error output, database state (no secrets!)

## Related Documentation

- [Webhook Management User Guide](/docs/user-guide/webhook-management.md)
- [Webhook API Documentation](/docs/api/webhooks.md)
- [Repository API Documentation](/docs/api/repositories.md)
