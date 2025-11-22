# Slack Integration - Quick Start

## 🚀 Ready to Test!

The complete Slack integration is ready to test. Here's how to get started in **5 minutes**.

## Step 1: Configure Slack (2 minutes)

Add to your `.env` file:

```bash
# Get this from https://api.slack.com/apps (OAuth & Permissions)
SLACK_TOKEN=xoxb-your-bot-token-here

# Get this from https://api.slack.com/apps (Basic Information)
SLACK_SIGNING_SECRET=your-signing-secret-here

# Channel configuration (optional - these are defaults)
SLACK_INCIDENTS_CHANNEL=#incidents
SLACK_APPROVALS_CHANNEL=#devflowfix-approvals
```

**Quick Setup:**
1. Go to https://api.slack.com/apps
2. Create new app or select existing
3. Add bot token scopes: `chat:write`, `chat:write.public`, `channels:read`
4. Install app to workspace
5. Copy "Bot User OAuth Token" → `SLACK_TOKEN`
6. Copy "Signing Secret" → `SLACK_SIGNING_SECRET`

## Step 2: Invite Bot to Channels (30 seconds)

In Slack:
```
/invite @DevFlowFix
```

Do this in both:
- `#incidents` (or your configured incidents channel)
- `#devflowfix-approvals` (or your configured approvals channel)

## Step 3: Run Quick Test (1 minute)

```bash
python quick_test_slack.py
```

**What it does:**
- ✅ Sends low confidence incident → approval request (you click button)
- ✅ Sends high confidence incident → auto-fix notification

**Expected output:**
```
======================================================================
QUICK SLACK INTEGRATION TEST
======================================================================

✅ Configuration OK
   Incidents Channel: #incidents
   Approvals Channel: #devflowfix-approvals

----------------------------------------------------------------------
TEST 1: Low Confidence Incident (72%) - Requires Approval
----------------------------------------------------------------------

   1. Sending notification to #incidents...
      ✅ Notification sent (ts: 1700000000.123456)

   2. Sending approval request to #devflowfix-approvals...
      ✅ Approval request sent (ts: 1700000000.123457)

      👉 Go to #devflowfix-approvals and click Approve/Reject

----------------------------------------------------------------------
TEST 2: High Confidence Incident (96%) - Auto-Fix
----------------------------------------------------------------------

   1. Auto-executing remediation (high confidence)...
      ✅ Remediation completed

   2. Sending success notification to #incidents...
      ✅ Notification sent (ts: 1700000000.123458)

======================================================================
TEST COMPLETE!
======================================================================

✅ Check your Slack channels:
   • #incidents - for notifications
   • #devflowfix-approvals - for approval request

💡 Click the Approve/Reject button to test the callback flow
   (Note: Webhook must be configured for callbacks to work)
```

## What You'll See in Slack

### In #incidents:

**Low Confidence Incident:**
```
🔥 Incident Detected

Incident ID: inc_test_low_143022
Source: GITHUB
Severity: 🔥 MEDIUM

Error Message:
npm peer dependency conflict

Context:
• Repository: example/repo
• Workflow: CI Build

🔍 Analysis Results
Root Cause: Conflicting webpack peer dependencies
Confidence: 🟠 72.0% (Medium)

📊 Similar Incidents Found: 1
```

**High Confidence Success:**
```
✅ Remediation Success

Incident ID: inc_test_high_143027
Status: ✅ Success

Details:
Workflow rerun completed successfully

⏱️ Resolved in 1s
```

### In #devflowfix-approvals:

```
⚠️ Remediation Approval Required

Incident ID: inc_test_low_143022
Source: GITHUB
Severity: ⚠️ MEDIUM

Root Cause: Conflicting webpack peer dependencies
AI Confidence: 🟠 72.0% (Medium)

🔧 Proposed Remediation
Action: github_rerun_workflow
Risk Level: 🟢 LOW

⏰ This request will expire Nov 22, 2024 at 3:00 PM

[✅ Approve]  [❌ Reject]
```

## Test Scenarios Explained

### ✅ Scenario 1: Low Confidence (Approval Required)

**Confidence:** 72% (below 85% threshold)  
**Flow:**
1. Incident detected → notification sent to #incidents
2. Approval request sent to #approvals with buttons
3. **You click Approve** → remediation executes
4. Message updates to show approval

**Why:** Low confidence incidents need human verification before auto-fixing.

### ✅ Scenario 2: High Confidence (Auto-Fix)

**Confidence:** 96% (above 85% threshold)  
**Flow:**
1. Incident detected → auto-executes immediately
2. Success notification sent to #incidents

**Why:** High confidence incidents are safe to auto-fix.

## Advanced Testing

### Run Full Test Suite

For comprehensive testing with more scenarios:

```bash
python test_slack_integration_manual.py
```

This includes:
- ✅ Low confidence with approval
- ✅ High confidence auto-fix
- ✅ Similar incidents display
- ✅ Rich message formatting
- ✅ Execution logging

### Run Automated Tests

For CI/CD integration:

```bash
pytest tests/integration/test_slack_integration.py -v
```

Tests include:
- Low confidence approval workflow
- High confidence auto-fix workflow
- Approval rejection flow
- Complete end-to-end integration

## Troubleshooting

### ❌ "Slack token not configured"

**Fix:** Add `SLACK_TOKEN=xoxb-...` to `.env`

### ❌ "Channel not found"

**Fix:** Invite bot to channel: `/invite @DevFlowFix`

### ❌ Buttons not working

**Fix:** You need to set up webhook for callbacks (see below)

## Next: Set Up Webhooks for Button Callbacks

To make the Approve/Reject buttons work, you need a webhook endpoint:

### 1. Quick Setup with ngrok (for testing)

```bash
# Terminal 1: Start your app
python -m uvicorn app.main:app --reload

# Terminal 2: Start ngrok
ngrok http 8000
```

### 2. Configure Slack App

1. Go to https://api.slack.com/apps → Your App
2. **Interactivity & Shortcuts** → Enable Interactivity
3. Set Request URL: `https://your-ngrok-url.ngrok.io/api/v1/webhooks/slack/interactions`
4. Save Changes

### 3. Test Button Clicks

Now when you click Approve/Reject in Slack:
- Callback hits your local server
- Remediation executes automatically
- Message updates to show decision

See `SLACK_TESTING_GUIDE.md` for detailed webhook setup.

## 📚 Documentation

- **Quick Start:** `README_SLACK_QUICK_START.md` (this file)
- **Testing Guide:** `SLACK_TESTING_GUIDE.md` - Complete testing documentation
- **Implementation Summary:** `SLACK_INTEGRATION_SUMMARY.md` - Technical details

## 🎯 What's Working

✅ Slack client with authentication  
✅ Rich incident notifications  
✅ Interactive approval workflow  
✅ Confidence-based decision making  
✅ Auto-fix for high confidence  
✅ Approval required for low confidence  
✅ Similar incidents display  
✅ Remediation status tracking  
✅ Button callbacks (with webhook)  
✅ Comprehensive tests  

## 🚀 Production Deployment

When ready for production:

1. **Set up production webhook endpoint**
   ```python
   # app/api/v1/webhooks/slack.py
   @router.post("/slack/interactions")
   async def handle_slack_interaction(request: Request):
       # Handle button callbacks
       ...
   ```

2. **Update Slack app with production URL**
   - Request URL: `https://your-domain.com/api/v1/webhooks/slack/interactions`

3. **Configure environment variables**
   - Use AWS Secrets Manager or similar for tokens
   - Set production channels

4. **Monitor and alert**
   - Track notification delivery
   - Monitor approval response times
   - Alert on webhook failures

## Need Help?

- Check `SLACK_TESTING_GUIDE.md` for detailed troubleshooting
- Review Slack API docs: https://api.slack.com/docs
- Test message formatting: https://app.slack.com/block-kit-builder

---

**Ready to see it in action?** Run `python quick_test_slack.py` now! 🚀
