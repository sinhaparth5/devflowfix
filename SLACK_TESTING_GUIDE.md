# Slack Integration Testing Guide

## Overview

This guide covers testing the complete Slack integration for DevFlowFix, including:
1. **Low Confidence Incident** → Slack notification + approval request → manual approval → execution
2. **High Confidence Incident** → Auto-fix → success notification
3. **Rejection Flow** → Approval request → manual rejection → no execution

## Prerequisites

### 1. Slack Configuration

Add to your `.env` file:

```bash
# Slack Bot Token (starts with xoxb-)
SLACK_TOKEN=xoxb-your-bot-token-here

# Slack Signing Secret (for webhook verification)
SLACK_SIGNING_SECRET=your-signing-secret-here

# Slack Channels
SLACK_INCIDENTS_CHANNEL=#incidents
SLACK_APPROVALS_CHANNEL=#devflowfix-approvals
```

### 2. Slack Bot Permissions

Your Slack bot needs these OAuth scopes:
- `chat:write` - Post messages
- `chat:write.public` - Post to public channels without joining
- `channels:read` - List channels
- `users:read` - Get user info
- `search:read` - Search messages (for RAG)

### 3. Install Slack Bot

Install the bot to your workspace and invite it to the channels:
```
/invite @DevFlowFix
```

## Test Scenarios

### Scenario 1: Low Confidence Incident (Requires Approval)

**What it tests:**
- Incident notification to #incidents channel
- Approval request to #approvals channel with interactive buttons
- Button click callback handling
- Remediation execution on approval

**How to run:**

```bash
# Run manual test script
python test_slack_integration_manual.py
```

**Expected behavior:**
1. Script creates incident with 72% confidence
2. Sends rich notification to #incidents with:
   - Incident details (ID, source, severity, error)
   - Root cause analysis
   - Confidence score with emoji
   - Similar incidents
   - Context (repository, workflow, etc.)
3. Sends approval request to #approvals with:
   - All incident details
   - Remediation plan
   - Risk level
   - Interactive Approve/Reject buttons
4. Wait for you to click a button in Slack
5. On approval: executes remediation automatically
6. Updates message to show decision

**In Slack, you'll see:**

```
🔥 Incident Detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Incident ID: inc_low_20241122_143022
Source: GITHUB
Severity: 🔥 MEDIUM
Timestamp: Nov 22, 2024 at 2:30 PM

Error Message:
npm ERR! ERESOLVE could not resolve peer dependency conflict

Context:
• Repository: devflowfix-new/example-app
• Workflow: CI Build and Test
• Branch: feature/upgrade-dependencies

🔍 Analysis Results
Root Cause: Conflicting webpack peer dependencies...
Fixability: 🤖 AUTO
Confidence: 🟠 72.0% (Medium)

📊 Similar Incidents Found: 3
1. inc_20241120_143022 • 89.0% similar • ✅ success
2. inc_20241119_091533 • 85.0% similar • ✅ success
3. inc_20241118_164408 • 78.0% similar • ✅ success
```

And in #approvals:

```
⚠️ Remediation Approval Required
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Incident Details]
[Remediation Plan]

⏰ This request will expire Nov 22, 2024 at 3:00 PM

[✅ Approve]  [❌ Reject]
```

### Scenario 2: High Confidence Incident (Auto-Fix)

**What it tests:**
- Automatic remediation execution (no approval)
- Success notification to #incidents

**How to run:**

Same script will run this after Scenario 1:
```bash
python test_slack_integration_manual.py
```

**Expected behavior:**
1. Script creates incident with 96% confidence
2. Auto-executes remediation immediately (no approval needed)
3. Sends success notification to #incidents with:
   - Incident details
   - Remediation status: ✅ SUCCESS
   - Resolution time

**In Slack, you'll see:**

```
ℹ️ Incident Detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Incident ID: inc_high_20241122_143027
Source: GITHUB
Severity: ℹ️ LOW
Confidence: 🟢 96.0% (Very High)

🔧 Remediation Status
Status: ✅ SUCCESS
Message: Workflow rerun initiated successfully
Resolution Time: 2s

DevFlowFix AI • Nov 22, 2024 at 2:30 PM
```

### Scenario 3: Rejection Flow

**What it tests:**
- Approval rejection
- No remediation execution
- Message update to show rejection

**How to test:**

Run the script and click **❌ Reject** instead of Approve.

**Expected behavior:**
1. Approval request sent to #approvals
2. Click Reject button
3. Message updates to show rejection
4. No remediation is executed

**Updated message shows:**

```
❌ Remediation REJECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Incident ID: inc_low_20241122_143022
Decision: ❌ REJECTED
Decided By: john.doe
Decided At: Nov 22, 2024 at 2:31 PM

❌ Remediation cancelled
```

## Automated Tests

Run pytest for automated integration tests:

```bash
# Run all Slack integration tests
pytest tests/integration/test_slack_integration.py -v

# Run specific test
pytest tests/integration/test_slack_integration.py::test_low_confidence_approval_workflow -v

# Run with output
pytest tests/integration/test_slack_integration.py -v -s
```

**Tests included:**
- ✅ `test_low_confidence_approval_workflow` - Full approval flow
- ✅ `test_high_confidence_auto_fix_workflow` - Auto-fix flow
- ✅ `test_approval_rejection` - Rejection flow
- ✅ `test_complete_slack_integration_flow` - End-to-end

## Webhook Integration (For Production)

To handle button callbacks in production, you need to set up a webhook endpoint:

### 1. Create Webhook Endpoint

```python
# app/api/v1/webhooks/slack.py

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

@router.post("/slack/interactions")
async def handle_slack_interaction(request: Request):
    """Handle Slack interactive button callbacks."""
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify Slack signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not approval_adapter.verify_slack_request(
        request_body=body.decode(),
        timestamp=timestamp,
        signature=signature,
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse payload
    payload = await request.json()
    
    # Handle callback
    result = await approval_adapter.handle_callback(payload)
    
    return {"ok": True}
```

### 2. Configure Slack App

1. Go to https://api.slack.com/apps
2. Select your app
3. Go to **Interactivity & Shortcuts**
4. Enable **Interactivity**
5. Set Request URL: `https://your-domain.com/api/v1/webhooks/slack/interactions`
6. Save changes

### 3. Test Webhook

```bash
# Use ngrok for local testing
ngrok http 8000

# Update Slack app Request URL to ngrok URL
# Click buttons in Slack - callbacks will hit your local server
```

## Troubleshooting

### Issue: "Slack token not configured"

**Solution:** Add `SLACK_TOKEN` to your `.env` file with your bot token (starts with `xoxb-`).

### Issue: "Channel not found"

**Solution:** 
- Invite the bot to the channel: `/invite @DevFlowFix`
- Or use channel ID instead of name in config

### Issue: "Invalid signature"

**Solution:** 
- Verify `SLACK_SIGNING_SECRET` is correct
- Check webhook payload is not being modified
- Ensure timestamp is recent (Slack rejects old requests)

### Issue: Buttons not working

**Solution:**
- Verify Interactivity is enabled in Slack app settings
- Check Request URL is correct and accessible
- Review webhook logs for errors

### Issue: Messages not formatting correctly

**Solution:**
- Check Slack Block Kit syntax
- Use Slack's Block Kit Builder to validate: https://app.slack.com/block-kit-builder
- Ensure emoji are properly escaped

## Expected Results Summary

| Scenario | Confidence | Approval? | Channels | Result |
|----------|------------|-----------|----------|--------|
| Low Confidence | 72% | Required | #incidents + #approvals | Waits for approval, then executes |
| High Confidence | 96% | Not required | #incidents only | Auto-executes, sends success notification |
| Rejection | N/A | Rejected | #approvals | No execution, message updated |

## Next Steps

After successful testing:

1. **Integrate with RemediatorService** - Replace mock callback with actual remediation
2. **Set up webhook endpoint** - Handle button callbacks in production
3. **Add to CI/CD pipeline** - Automatically notify on failures
4. **Configure channels** - Set up proper incident and approval channels
5. **Add monitoring** - Track notification delivery and approval times

## Additional Resources

- [Slack Block Kit Builder](https://app.slack.com/block-kit-builder)
- [Slack API Documentation](https://api.slack.com/docs)
- [Interactive Messages Guide](https://api.slack.com/messaging/interactivity)
- [Verifying Requests from Slack](https://api.slack.com/authentication/verifying-requests-from-slack)
