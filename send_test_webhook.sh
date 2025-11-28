#!/bin/bash
# Send test webhook to DevFlowFix

echo "============================================================"
echo "Sending Test Webhook to DevFlowFix"
echo "============================================================"
echo ""

# GitHub webhook secret from database for user usr_4948120fa134
WEBHOOK_SECRET="PdDjqR-7iwug0uYblIBnsDUPFXC-9yordsXDAHNzCAk"

# Test payload
PAYLOAD='{
  "action": "completed",
  "workflow_run": {
    "id": 123456789,
    "name": "CI Pipeline Test",
    "head_branch": "main",
    "head_sha": "abc123def456789",
    "conclusion": "failure",
    "status": "completed",
    "html_url": "https://github.com/test/repo/actions/runs/123456789"
  },
  "repository": {
    "full_name": "test-org/test-repo",
    "name": "test-repo",
    "owner": {
      "login": "test-org"
    },
    "html_url": "https://github.com/test-org/test-repo"
  },
  "error_message": "Build failed: Unit tests failed in test_auth.py",
  "error_log": "FAILED tests/test_auth.py::test_login - AssertionError: Expected 200, got 401\n  File \"tests/test_auth.py\", line 45, in test_login\n    assert response.status_code == 200",
  "severity": "high",
  "context": {
    "build_number": "1234",
    "triggered_by": "push"
  }
}'

# Server URL
URL="http://localhost:8000/api/v1/webhook/github/usr_4948120fa134"

# Generate HMAC signature (GitHub uses sha256)
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | sed 's/^.* //')

echo "Sending webhook to: $URL"
echo "Using webhook signature: sha256=$SIGNATURE"
echo ""

# Send the webhook with signature
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: workflow_run" \
  -H "X-GitHub-Delivery: test-delivery-$(date +%s)" \
  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
  -d "$PAYLOAD")

# Extract status code and body
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "Response Status: $HTTP_CODE"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    echo "Webhook accepted successfully!"
    echo ""
    echo "Response:"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
    echo ""
    echo "============================================================"
    echo " TEST PASSED"
    echo "============================================================"
    echo ""
    echo "Next steps:"
    echo "1. Check the server logs for 'incident_created' message"
    echo "2. Verify no 'Circular reference detected' errors"
    echo "3. Look for 'embedding_generated' if NVIDIA key is configured"
    echo ""
else
    echo "Webhook failed with status: $HTTP_CODE"
    echo ""
    echo "Response:"
    echo "$BODY"
    echo ""
    echo "============================================================"
    echo "TEST FAILED"
    echo "============================================================"
    exit 1
fi
