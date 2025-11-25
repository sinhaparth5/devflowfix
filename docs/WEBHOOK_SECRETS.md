# GitHub Webhook Secret Management

## Overview

This system generates unique webhook secrets for each user instead of using hardcoded environment variables. Each user gets their own cryptographically secure secret for webhook signature verification.

## Features

- ✅ **Per-user secrets**: Each user has their own unique webhook secret
- ✅ **Cryptographically secure**: 256-bit random secrets (same strength as GitHub's)
- ✅ **No hardcoded values**: Secrets are generated dynamically and stored in database
- ✅ **Easy regeneration**: Users can regenerate their secrets at any time
- ✅ **Testing tools**: Built-in endpoints to test signature generation

## Quick Start

### 1. Run Database Migration

```bash
# Add the column to the database
psql -h <host> -p <port> -U <user> -d <database> -f scripts/add_github_webhook_secret_column.sql
```

Or use the Python script:

```bash
python scripts/setup_webhook_secrets.py --user-id shine
```

### 2. Generate Webhook Secret for User

**Option A: Via API (recommended)**

```bash
curl -X POST "http://localhost:8000/api/v1/webhook/secret/generate?user_id=shine"
```

**Option B: Via Python Script**

```bash
python scripts/setup_webhook_secrets.py --user-id shine
```

**Response:**
```json
{
  "success": true,
  "user_id": "shine",
  "webhook_secret": "1zCC4or5bOkGQJYBi8uRUcJVpxvWS3nAoTJ0hYb7RoI",
  "instructions": {
    "step_1": "Copy the webhook_secret value above",
    "step_2": "Go to your GitHub repository → Settings → Webhooks",
    "step_3": "Add or edit your webhook",
    "step_4": "Paste the secret in the 'Secret' field",
    "step_5": "Add custom header: X-DevFlowFix-User-ID: shine",
    "note": "⚠️ This is the ONLY time the secret will be displayed. Save it now!"
  }
}
```

### 3. Configure GitHub Webhook

1. Go to your GitHub repository
2. Settings → Webhooks → Add webhook
3. Configure:
   - **Payload URL**: `https://your-domain.com/api/v1/webhook/github`
   - **Content type**: `application/json`
   - **Secret**: Paste the generated secret (e.g., `1zCC4or5bOkGQJYBi8uRUcJVpxvWS3nAoTJ0hYb7RoI`)
   - **Events**: Select "Workflow runs" and "Check runs"

4. **Important**: Include user ID in webhook
   - GitHub doesn't support custom headers in webhook config
   - Use query parameter: `https://your-domain.com/api/v1/webhook/github?user_id=shine`
   - Or configure your reverse proxy to add `X-DevFlowFix-User-ID` header

### 4. Test Your Webhook

**Generate test signature:**

```bash
curl -X POST "http://localhost:8000/api/v1/webhook/secret/test?user_id=shine" \
  -H "Content-Type: application/json" \
  -d '{"action": "completed", "workflow_run": {"id": 123, "conclusion": "failure"}}'
```

**Send test webhook:**

```bash
curl -X POST "http://localhost:8000/api/v1/webhook/github" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -H "X-DevFlowFix-User-ID: shine" \
  -H "X-Hub-Signature-256: sha256=<signature-from-previous-step>" \
  -d '{"action": "completed", "workflow_run": {"id": 123, "conclusion": "failure"}}'
```

## API Endpoints

### Generate New Secret

```http
POST /api/v1/webhook/secret/generate?user_id=<user_id>
```

Generates a new webhook secret for the user. **This is the only time the secret is shown in plain text!**

### Get Secret Info

```http
GET /api/v1/webhook/secret/info?user_id=<user_id>
```

Get information about the user's webhook configuration (without revealing the secret).

### Test Signature Generation

```http
POST /api/v1/webhook/secret/test?user_id=<user_id>
Content-Type: application/json

{your webhook payload}
```

Generate a test signature to verify your webhook setup.

## Architecture

### Before (Hardcoded)
```
GitHub → Webhook → Server
                    ↓
            ENV: GITHUB_WEBHOOK_SECRET (same for all)
                    ↓
            Verify signature
```

### After (Per-User)
```
GitHub → Webhook (with user_id) → Server
                                    ↓
                    Lookup user in database
                                    ↓
                    Get user.github_webhook_secret
                                    ↓
                    Verify signature with user's secret
```

## Security Features

1. **Cryptographically secure random generation**: Uses Python's `secrets` module
2. **256-bit entropy**: Same strength as GitHub's secrets
3. **URL-safe encoding**: Base64 encoded without padding
4. **Database storage**: Secrets stored securely in PostgreSQL
5. **HMAC-SHA256 verification**: Industry-standard signature algorithm
6. **One-time display**: Secrets only shown once during generation

## Database Schema

```sql
ALTER TABLE users 
ADD COLUMN github_webhook_secret TEXT;
```

The secret is stored as a TEXT column in the `users` table.

## Example Secret Format

```
1zCC4or5bOkGQJYBi8uRUcJVpxvWS3nAoTJ0hYb7RoI
```

- Length: 43 characters
- Encoding: URL-safe Base64 (no padding)
- Entropy: 256 bits
- Character set: `A-Za-z0-9_-`

## Troubleshooting

### "Invalid webhook signature"

1. Check that you're sending the `X-DevFlowFix-User-ID` header
2. Verify the secret in GitHub webhook settings matches the generated secret
3. Use the test endpoint to generate a valid signature
4. Check server logs for detailed verification info

### "User not found"

- Ensure the user_id in `X-DevFlowFix-User-ID` header matches a user in the database
- Check spelling and case sensitivity

### "GitHub webhook secret not configured"

- The user hasn't generated a webhook secret yet
- Run: `POST /api/v1/webhook/secret/generate?user_id=<user_id>`

## Migration from Environment Variable

If you're migrating from `GITHUB_WEBHOOK_SECRET` env var:

1. Generate secrets for all users: `python scripts/setup_webhook_secrets.py`
2. Update GitHub webhook configurations with new secrets
3. (Optional) Remove `GITHUB_WEBHOOK_SECRET` from environment

The system supports both methods during transition:
- If `X-DevFlowFix-User-ID` is provided → uses user's secret
- If not provided → falls back to `GITHUB_WEBHOOK_SECRET` env var (legacy)

## Best Practices

1. **Generate unique secrets per repository** (if needed)
2. **Rotate secrets periodically** (every 90 days recommended)
3. **Never commit secrets to version control**
4. **Use HTTPS for webhook endpoints**
5. **Monitor webhook delivery logs in GitHub**
6. **Save secrets immediately** when generated (they're only shown once)

## Support

For issues or questions, check:
- Server logs: Look for `github_webhook_*` and `webhook_secret_*` events
- GitHub webhook delivery logs: Settings → Webhooks → Recent Deliveries
- Test endpoints to verify signature generation
