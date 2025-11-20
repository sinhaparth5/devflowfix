# GitHub Webhook Setup Guide

This guide walks you through setting up GitHub webhooks for DevFlowFix to receive CI/CD failure notifications in real-time.

## Prerequisites

- GitHub repository with admin access
- DevFlowFix application running (locally or deployed)
- ngrok or similar tunneling service (for local development)

## Step 1: Generate Webhook Secret

Generate a secure random secret for webhook signature verification:

### Using PowerShell:
```powershell
# Generate a random 32-character secret
$secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
Write-Host "GITHUB_WEBHOOK_SECRET=$secret"
```

### Using Python:
```python
import secrets
secret = secrets.token_urlsafe(32)
print(f"GITHUB_WEBHOOK_SECRET={secret}")
```

### Using OpenSSL:
```bash
openssl rand -base64 32
```

**Save this secret** - you'll need it in the next steps.

## Step 2: Update .env File

Add the webhook secret to your `.env` file:

```bash
# GitHub Webhook Configuration
GITHUB_WEBHOOK_SECRET=your_generated_secret_here
```

**Important**: Never commit this secret to version control! Ensure `.env` is in your `.gitignore`.

## Step 3: Start Your Application

### For Local Development:

1. **Start DevFlowFix**:
   ```powershell
   # Using uvicorn
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   
   # Or using the Makefile
   make run
   ```

2. **Start ngrok tunnel** (in a separate terminal):
   ```powershell
   ngrok http 8000
   ```

3. **Note your ngrok URL**:
   - Look for the "Forwarding" line in ngrok output
   - Example: `https://abc123.ngrok.io -> http://localhost:8000`
   - Your webhook URL will be: `https://abc123.ngrok.io/webhooks/github`

### For Production Deployment:

Use your production domain:
- AWS Lambda: `https://your-api-gateway-url.amazonaws.com/webhooks/github`
- EC2/Server: `https://your-domain.com/webhooks/github`
- Docker: `https://your-domain.com/webhooks/github`

## Step 4: Configure GitHub Webhook

1. **Navigate to your GitHub repository**
   - Go to: `https://github.com/YOUR_USERNAME/YOUR_REPO`

2. **Open Webhook Settings**
   - Click **Settings** (top menu)
   - Click **Webhooks** (left sidebar)
   - Click **Add webhook** button

3. **Configure Webhook Details**

   | Field | Value |
   |-------|-------|
   | **Payload URL** | `https://your-ngrok-url/webhooks/github` |
   | **Content type** | `application/json` |
   | **Secret** | Paste your `GITHUB_WEBHOOK_SECRET` value |
   | **SSL verification** | ✅ Enable SSL verification |

4. **Select Events**

   Click "Let me select individual events" and choose:
   
   - ✅ **Workflow runs** (Primary - detects CI/CD failures)
   - ✅ **Pushes** (Track code changes)
   - ✅ **Check runs** (Additional CI/CD events)
   - ✅ **Pull requests** (Optional - for PR-based failures)
   - ✅ **Deployments** (Optional - for deployment failures)

5. **Activate Webhook**
   - ✅ Ensure "Active" checkbox is checked
   - Click **Add webhook** button

## Step 5: Verify Webhook Setup

### Test 1: Check Webhook Deliveries

1. Go to your webhook settings
2. Click on the webhook you just created
3. Scroll to **Recent Deliveries**
4. GitHub automatically sends a `ping` event
5. Look for:
   - ✅ Green checkmark (200 OK response)
   - ❌ Red X indicates configuration issue

### Test 2: Trigger a Workflow

1. Push a commit to trigger a workflow:
   ```powershell
   git commit --allow-empty -m "Test webhook trigger"
   git push
   ```

2. Check DevFlowFix logs for webhook reception:
   ```
   INFO: Received GitHub webhook event: workflow_run
   INFO: Webhook signature verified successfully
   ```

3. Verify in GitHub webhook deliveries tab

### Test 3: Use Verification Script

Run the included verification script:

```powershell
python scripts/verify_webhook_setup.py
```

This script will:
- ✅ Check if webhook secret is configured
- ✅ Verify endpoint is accessible
- ✅ Test signature verification
- ✅ Validate webhook configuration

## Step 6: Monitor Webhook Activity

### View Logs in DevFlowFix

```powershell
# Follow application logs
tail -f logs/devflowfix.log

# Or check recent webhook events
grep "webhook" logs/devflowfix.log | tail -20
```

### View Deliveries in GitHub

1. Go to Settings → Webhooks → Your webhook
2. Click **Recent Deliveries** tab
3. Click on any delivery to see:
   - Request headers
   - Payload
   - Response
   - Delivery time

## Troubleshooting

### Issue: "401 Unauthorized" Response

**Cause**: Webhook secret mismatch

**Solution**:
1. Verify secret in `.env` matches GitHub webhook secret
2. Restart DevFlowFix application
3. Re-deliver webhook from GitHub

### Issue: "Connection Refused" or "Timeout"

**Cause**: Application not accessible

**Solution**:
1. Verify application is running: `curl http://localhost:8000/health`
2. Check ngrok is running and forwarding correctly
3. Verify firewall rules allow incoming connections
4. Check webhook URL is correct

### Issue: "SSL Verification Failed"

**Cause**: ngrok free tier or invalid SSL certificate

**Solution**:
1. For ngrok: Ensure using HTTPS URL (not HTTP)
2. For production: Ensure valid SSL certificate
3. Temporarily disable SSL verification (dev only - NOT recommended)

### Issue: Webhook Not Triggering

**Cause**: Events not configured or workflow not running

**Solution**:
1. Verify "Workflow runs" event is selected
2. Check workflow actually ran in Actions tab
3. Verify webhook is "Active"
4. Check repository has GitHub Actions enabled

## Security Best Practices

### ✅ DO:
- Use strong, randomly generated webhook secrets (32+ characters)
- Store secrets in `.env` file (gitignored)
- Enable SSL verification
- Rotate webhook secrets periodically
- Monitor webhook delivery logs
- Use HTTPS endpoints only

### ❌ DON'T:
- Commit webhook secrets to version control
- Use weak or predictable secrets
- Disable SSL verification in production
- Share webhook URLs publicly
- Use HTTP endpoints (unencrypted)

## Advanced Configuration

### Multiple Repositories

To receive webhooks from multiple repositories:

1. Use the same webhook secret across all repos
2. Or configure per-repository secrets in database
3. Extract repository info from webhook payload:
   ```python
   repository = payload.get("repository", {}).get("full_name")
   ```

### Webhook Retry Logic

GitHub automatically retries failed webhook deliveries:
- Retries up to 3 times
- Exponential backoff between retries
- 30-second timeout per attempt

### Rate Limiting

GitHub webhook rate limits:
- No hard limit on webhook deliveries
- Consider implementing rate limiting in DevFlowFix
- Configure in `.env`:
  ```
  RATE_LIMIT_ENABLED=true
  RATE_LIMIT_REQUESTS=100
  RATE_LIMIT_WINDOW=60
  ```

## Webhook Payload Examples

### Workflow Run (Failure)
```json
{
  "action": "completed",
  "workflow_run": {
    "id": 1234567890,
    "name": "CI",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/owner/repo/actions/runs/1234567890",
    "head_branch": "main",
    "head_sha": "abc123def456"
  },
  "repository": {
    "full_name": "owner/repo"
  }
}
```

### Push Event
```json
{
  "ref": "refs/heads/main",
  "commits": [
    {
      "id": "abc123",
      "message": "Fix bug",
      "author": {
        "name": "Developer"
      }
    }
  ],
  "repository": {
    "full_name": "owner/repo"
  }
}
```

## Testing Locally

### Simulate Webhook Request

```powershell
# Using curl
$body = Get-Content -Raw test-payload.json
$signature = # compute HMAC-SHA256 signature
Invoke-WebRequest -Uri "http://localhost:8000/webhooks/github" `
    -Method POST `
    -Headers @{
        "X-Hub-Signature-256" = "sha256=$signature"
        "X-GitHub-Event" = "workflow_run"
        "Content-Type" = "application/json"
    } `
    -Body $body
```

### Use Webhook Testing Tool

```powershell
python scripts/test_webhook.py --event workflow_run --file examples/webhook_payloads/workflow_failure.json
```

## Next Steps

After webhook setup:

1. ✅ Test with real workflow failures
2. ✅ Configure Slack notifications
3. ✅ Set up auto-remediation rules
4. ✅ Configure confidence thresholds
5. ✅ Enable learning mode
6. ✅ Set up monitoring and alerting

## Resources

- [GitHub Webhooks Documentation](https://docs.github.com/en/webhooks)
- [Webhook Events and Payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [Securing Webhooks](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [ngrok Documentation](https://ngrok.com/docs)

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review application logs
3. Check GitHub webhook delivery details
4. Open an issue on GitHub
