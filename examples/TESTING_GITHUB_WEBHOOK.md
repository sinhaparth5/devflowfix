# Test Workflow for DevFlowFix Webhook

This workflow file can be used to test the GitHub webhook integration.

## Option 1: Create a Workflow That Always Fails

Create this file in your test repository at `.github/workflows/test-devflowfix.yml`:

```yaml
name: Test DevFlowFix Webhook
on:
  push:
    branches: [main, master]
  workflow_dispatch:

jobs:
  test-failure:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Intentional Failure
        run: |
          echo "Testing DevFlowFix webhook integration"
          echo "This step will fail intentionally"
          exit 1
```

## Option 2: Create a Workflow with Conditional Failure

Create this at `.github/workflows/test-devflowfix-conditional.yml`:

```yaml
name: Test DevFlowFix (Conditional)
on:
  push:
  workflow_dispatch:
    inputs:
      should_fail:
        description: 'Should this workflow fail?'
        required: true
        default: 'true'
        type: choice
        options:
          - 'true'
          - 'false'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Run Test
        run: |
          if [ "${{ github.event.inputs.should_fail || 'true' }}" == "true" ]; then
            echo "❌ Test failed (intentional for DevFlowFix testing)"
            exit 1
          else
            echo "✅ Test passed"
            exit 0
          fi
```

## How to Use

### Method 1: Push to Trigger
```bash
# Add the workflow file
git add .github/workflows/test-devflowfix.yml
git commit -m "Add DevFlowFix test workflow"
git push
```

### Method 2: Manual Trigger
1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select **Test DevFlowFix Webhook** workflow
4. Click **Run workflow** button
5. Click **Run workflow** to confirm

### Method 3: Re-run Existing Failed Workflow
1. Go to **Actions** tab
2. Find any failed workflow run
3. Click on it
4. Click **Re-run all jobs**

## What to Expect

When the workflow fails, DevFlowFix will:

1. ✅ Receive webhook from GitHub
2. ✅ Verify HMAC-SHA256 signature
3. ✅ Extract failure details from payload
4. ✅ Create incident in database with:
   - Incident ID (e.g., `gh_77ce79d8-c2cb-11f0-9143-2c980b10c563`)
   - Source: `github`
   - Severity: `critical` (for main/master), `high` (for staging), or `medium`
   - Repository name
   - Workflow name
   - Branch, commit SHA, author
   - Workflow run URL
   - Error logs

## Verify the Integration

Run the test script to check if incidents are being created:

```bash
python scripts/test_github_webhook.py
```

Or query the database directly:

```sql
SELECT 
    incident_id,
    source,
    severity,
    failure_type,
    context->>'repository' as repository,
    context->>'workflow_name' as workflow,
    context->>'branch' as branch,
    created_at
FROM incidents
WHERE source = 'github'
ORDER BY created_at DESC
LIMIT 10;
```

## Check Application Logs

Look for these log messages in your application:

```
github_webhook_received - Webhook received
github_webhook_signature_verified - Signature verified
github_workflow_failure_detected - Failure detected
incident_created - Incident saved to database
```

## Troubleshooting

### Workflow runs but no incident created

Check application logs for errors:
```bash
# If using journalctl
journalctl -u devflowfix -f

# If using file logging
tail -f logs/devflowfix.log

# If running in terminal
# Check the terminal output
```

### Database connection error

Verify database is running:
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test connection
psql -h localhost -U postgres -d devflowfix -c "SELECT 1;"
```

### Webhook not received

1. Check ngrok is running: `ngrok http 8000`
2. Verify webhook URL in GitHub matches ngrok URL
3. Check webhook deliveries in GitHub settings
4. Verify application is running: `curl http://localhost:8000/health`

## Clean Up

To stop getting failure notifications, you can:

1. Delete the test workflow file
2. Disable the workflow in GitHub Actions settings
3. Or change `exit 1` to `exit 0` to make it pass
