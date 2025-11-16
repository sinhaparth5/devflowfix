# GitHub Webhook Integration# GitHub Webhook Integration



Complete guide for integrating GitHub webhooks with DevFlowFix.Secure GitHub webhook integration with HMAC-SHA256 signature verification for DevFlowFix.



## Table of Contents## Overview



- [Overview](#overview)The GitHub webhook client provides robust signature verification and payload parsing for GitHub webhook events. It ensures that incoming webhook requests are authentic by validating the HMAC-SHA256 signature sent by GitHub.

- [Quick Start](#quick-start)

- [Webhook Events](#webhook-events)## Features

- [Security](#security)

- [API Reference](#api-reference)✅ **HMAC-SHA256 Signature Verification** - Cryptographically verify webhook authenticity  

- [Examples](#examples)✅ **Constant-Time Comparison** - Prevents timing attacks  

- [Testing](#testing)✅ **Multiple Event Type Support** - Handle workflow_run, check_run, push, and more  

- [Troubleshooting](#troubleshooting)✅ **Failure Detection** - Automatically detect failed workflows and checks  

✅ **Detail Extraction** - Parse useful information from webhook payloads  

## Overview✅ **FastAPI Integration** - Ready-to-use with FastAPI dependency injection  

✅ **Flask Support** - Works with Flask applications  

DevFlowFix uses GitHub webhooks to receive real-time notifications about workflow failures, check runs, and other CI/CD events. The webhook integration includes:✅ **Lambda Compatible** - Supports AWS Lambda function handlers  

✅ **Comprehensive Error Handling** - Custom exceptions for different failure modes

- **HMAC-SHA256 signature verification** for security

- **Event parsing** for workflow_run, check_run, push, and pull_request events## Configuration

- **Failure detection** with detailed error extraction

- **Async/sync support** for various deployment scenarios### Environment Variable



## Quick StartAdd to your `.env` file:



### 1. Set Up Webhook Secret```bash

GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

```bash```

# Generate a secure random secret

python -c "import secrets; print(secrets.token_hex(32))"**⚠️ Important**: This secret must match the secret configured in your GitHub webhook settings.



# Add to .env file### Generating a Secure Secret

GITHUB_WEBHOOK_SECRET=your_generated_secret_here

``````bash

# On Linux/Mac

### 2. Configure GitHub Webhookopenssl rand -hex 32



1. Go to your GitHub repository → Settings → Webhooks → Add webhook# On Windows (PowerShell)

2. **Payload URL**: `https://your-domain.com/api/v1/webhooks/github`[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))

3. **Content type**: `application/json`

4. **Secret**: Use the same secret from step 1# Python

5. **Events**: Select individual events:python -c "import secrets; print(secrets.token_hex(32))"

   - Workflow runs```

   - Check runs

   - Pushes### GitHub Webhook Setup

   - Pull requests

1. Go to your GitHub repository → Settings → Webhooks → Add webhook

### 3. Use the Client2. Set Payload URL to your endpoint (e.g., `https://your-domain.com/webhooks/github`)

3. Set Content type to `application/json`

```python4. Enter the same secret you configured in `.env`

from app.adapters.external.github.webhooks import GitHubWebhookClient5. Select events to subscribe to:

from app.core.config import settings   - ✅ Workflow runs

   - ✅ Check runs

# Initialize client   - ✅ Pushes

webhook_client = GitHubWebhookClient(secret=settings.GITHUB_WEBHOOK_SECRET)   - ✅ Pull requests (optional)



# In your webhook endpoint## Usage

@app.post("/api/v1/webhooks/github")

async def github_webhook(request: Request):### Basic Usage

    body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")```python

    from app.adapters.external.github import GitHubWebhookClient

    # Verify and parse

    event = webhook_client.verify_and_parse(# Initialize client (uses GITHUB_WEBHOOK_SECRET from env)

        payload=body,client = GitHubWebhookClient()

        signature=signature,

        event_type=request.headers.get("X-GitHub-Event", "")# Or provide secret explicitly

    )client = GitHubWebhookClient(webhook_secret="your_secret")

    

    # Check if it's a failure# Verify signature

    if webhook_client.is_workflow_failure(event):is_valid = client.verify_signature(

        details = webhook_client.extract_failure_details(event)    payload_body=request.body,  # Raw bytes

        # Process the failure...    signature_header=request.headers.get("X-Hub-Signature-256")

    )

    return {"status": "received"}

```if not is_valid:

    return {"error": "Invalid signature"}, 401

## Webhook Events```



### Supported Event Types### FastAPI Integration



| Event Type | Trigger | Use Case |```python

|------------|---------|----------|from fastapi import FastAPI, Request, HTTPException, Header

| `workflow_run` | Workflow completes | Detect CI/CD failures |from app.adapters.external.github import GitHubWebhookClient, WebhookSignatureError

| `check_run` | Check run completes | Catch test/lint failures |

| `push` | Code pushed | Track commits |app = FastAPI()

| `pull_request` | PR opened/updated | Monitor PR changes |webhook_client = GitHubWebhookClient()



### Event Structure@app.post("/webhooks/github")

async def github_webhook(

#### workflow_run Event    request: Request,

    x_hub_signature_256: str = Header(None),

```json    x_github_event: str = Header(None),

{):

  "action": "completed",    body = await request.body()

  "workflow_run": {    

    "id": 1234567890,    try:

    "name": "CI",        payload = webhook_client.verify_and_parse(

    "head_branch": "main",            payload_body=body,

    "head_sha": "abc123...",            signature_header=x_hub_signature_256,

    "status": "completed",            event_type=x_github_event,

    "conclusion": "failure",        )

    "html_url": "https://github.com/owner/repo/actions/runs/1234567890",    except WebhookSignatureError:

    "run_started_at": "2025-11-11T10:00:00Z",        raise HTTPException(status_code=401, detail="Invalid signature")

    "created_at": "2025-11-11T09:59:00Z",    

    "updated_at": "2025-11-11T10:05:00Z"    # Process payload based on event type

  },    if x_github_event == "workflow_run":

  "repository": {        if webhook_client.is_workflow_failure(payload):

    "id": 123456,            details = webhook_client.extract_failure_details(payload)

    "name": "repo",            # Handle failure

    "full_name": "owner/repo",            return {"status": "failure_detected", "details": details}

    "html_url": "https://github.com/owner/repo"    

  }    return {"status": "received"}

}```

```

### Convenience Function

#### check_run Event

```python

```jsonfrom app.adapters.external.github import verify_github_webhook

{

  "action": "completed",@app.post("/webhooks/github/simple")

  "check_run": {async def simple_webhook(request: Request):

    "id": 9876543210,    body = await request.body()

    "name": "test",    signature = request.headers.get("X-Hub-Signature-256")

    "status": "completed",    

    "conclusion": "failure",    if not verify_github_webhook(body, signature):

    "started_at": "2025-11-11T10:00:00Z",        raise HTTPException(status_code=401, detail="Invalid signature")

    "completed_at": "2025-11-11T10:05:00Z",    

    "output": {    # Process webhook

      "title": "Test Failed",    return {"status": "ok"}

      "summary": "3 tests failed",```

      "text": "AssertionError: expected True to be False"

    },### Comprehensive Validation

    "html_url": "https://github.com/owner/repo/runs/9876543210"

  }```python

}# Validates signature, event type, and payload in one call

```is_valid, error, payload = webhook_client.validate_webhook_request(

    payload_body=request.body,

## Security    headers=dict(request.headers)

)

### Signature Verification

if not is_valid:

All webhook requests MUST be verified using HMAC-SHA256 signatures:    return {"error": error}, 401



```python# Process payload

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:```

    """

    Verify GitHub webhook signature using HMAC-SHA256.## Webhook Events

    

    Args:### Supported Event Types

        payload: Raw request body (bytes)

        signature: X-Hub-Signature-256 header value#### workflow_run

        secret: Webhook secret from environmentTriggered when a GitHub Actions workflow completes.

        

    Returns:```python

        True if signature is validif x_github_event == "workflow_run":

            if webhook_client.is_workflow_failure(payload):

    Raises:        details = webhook_client.extract_failure_details(payload)

        ValueError: If signature format is invalid        # Details include:

    """        # - workflow_name

    if not signature.startswith("sha256="):        # - run_id

        raise ValueError("Invalid signature format")        # - conclusion

            # - repository

    expected_signature = hmac.new(        # - branch

        key=secret.encode(),        # - commit_sha

        msg=payload,        # - html_url

        digestmod=hashlib.sha256```

    ).hexdigest()

    #### check_run

    received_signature = signature[7:]  # Remove "sha256=" prefixTriggered when a check run completes.

    

    return hmac.compare_digest(expected_signature, received_signature)```python

```if x_github_event == "check_run":

    if webhook_client.is_workflow_failure(payload):

### Best Practices        details = webhook_client.extract_failure_details(payload)

        # Process check failure

1. **Always verify signatures** - Never trust unverified webhook data```

2. **Use constant-time comparison** - Prevents timing attacks (`hmac.compare_digest`)

3. **Rotate secrets regularly** - Update webhook secret every 90 days#### push

4. **Log verification failures** - Monitor for potential attacksTriggered on git push.

5. **Use HTTPS only** - Never accept webhooks over HTTP

6. **Validate event types** - Only process expected event types```python

7. **Rate limiting** - Implement rate limits on webhook endpointsif x_github_event == "push":

    repository = payload["repository"]["full_name"]

### Environment Variables    branch = payload["ref"]

    commits = payload["commits"]

```bash```

# Required

GITHUB_WEBHOOK_SECRET=your_secret_here## API Reference



# Optional (for enhanced security)### GitHubWebhookClient

WEBHOOK_ALLOWED_IPS=192.30.252.0/22,185.199.108.0/22,140.82.112.0/20

WEBHOOK_RATE_LIMIT=100  # requests per minute#### `__init__(webhook_secret: Optional[str] = None)`

```Initialize the client with webhook secret.



## API Reference**Parameters:**

- `webhook_secret`: GitHub webhook secret (falls back to `GITHUB_WEBHOOK_SECRET` env var)

### GitHubWebhookClient

**Raises:**

Main client for webhook handling.- `ValueError`: If secret not provided and not in environment



#### Constructor#### `verify_signature(payload_body: bytes, signature_header: str) -> bool`

Verify webhook signature using HMAC-SHA256.

```python

def __init__(self, secret: str):**Parameters:**

    """- `payload_body`: Raw request body as bytes

    Initialize webhook client.- `signature_header`: Value of `X-Hub-Signature-256` header

    

    Args:**Returns:**

        secret: GitHub webhook secret for signature verification- `True` if signature is valid, `False` otherwise

    """

```#### `verify_and_parse(payload_body: bytes, signature_header: str, event_type: Optional[str] = None) -> Dict[str, Any]`

Verify signature and parse JSON payload.

#### Methods

**Parameters:**

##### verify_signature- `payload_body`: Raw request body as bytes

- `signature_header`: Value of `X-Hub-Signature-256` header

```python- `event_type`: Value of `X-GitHub-Event` header (optional)

def verify_signature(self, payload: bytes, signature: str) -> bool:

    """**Returns:**

    Verify webhook signature.- Parsed webhook payload as dictionary

    

    Args:**Raises:**

        payload: Raw request body- `WebhookSignatureError`: If signature verification fails

        signature: X-Hub-Signature-256 header- `WebhookPayloadError`: If payload parsing fails

        

    Returns:#### `is_workflow_failure(payload: Dict[str, Any]) -> bool`

        True if validCheck if webhook represents a workflow failure.

        

    Raises:**Returns:**

        ValueError: Invalid signature format- `True` if workflow failed, timed out, or requires action

    """

```#### `extract_failure_details(payload: Dict[str, Any]) -> Dict[str, Any]`

Extract failure details from webhook payload.

##### verify_and_parse

**Returns:**

```pythonDictionary with keys:

def verify_and_parse(- `workflow_name`: Name of the workflow

    self,- `run_id`: Workflow run ID

    payload: bytes,- `conclusion`: Failure conclusion (failure, timed_out, etc.)

    signature: str,- `repository`: Repository full name (owner/repo)

    event_type: str- `branch`: Branch name

) -> Dict[str, Any]:- `commit_sha`: Commit SHA

    """- `html_url`: URL to workflow run

    Verify signature and parse JSON payload.

    #### `is_retry_eligible(payload: Dict[str, Any]) -> bool`

    Args:Determine if failed workflow can be automatically retried.

        payload: Raw request body

        signature: X-Hub-Signature-256 header**Returns:**

        event_type: X-GitHub-Event header- `True` if eligible for retry

        

    Returns:#### `validate_webhook_request(payload_body: bytes, headers: Dict[str, str]) -> Tuple[bool, Optional[str], Optional[Dict]]`

        Parsed webhook eventComprehensive webhook validation.

        

    Raises:**Returns:**

        ValueError: Invalid signature or JSONTuple of `(is_valid, error_message, parsed_payload)`

    """

```### Static Methods



##### is_workflow_failure#### `extract_event_type(headers: Dict[str, str]) -> Optional[str]`

Extract GitHub event type from headers.

```python

def is_workflow_failure(self, event: Dict[str, Any]) -> bool:#### `extract_delivery_id(headers: Dict[str, str]) -> Optional[str]`

    """Extract unique delivery ID from headers.

    Check if event represents a workflow failure.

    #### `get_workflow_logs_url(repository: str, run_id: int, job_id: Optional[int] = None) -> str`

    Args:Generate URL for workflow logs.

        event: Parsed webhook event

        ## Security Best Practices

    Returns:

        True if workflow/check failed### 1. Always Verify Signatures

    """```python

```# ❌ Bad - No verification

payload = json.loads(request.body)

##### extract_failure_details

# ✅ Good - Always verify

```pythonif not webhook_client.verify_signature(body, signature):

def extract_failure_details(self, event: Dict[str, Any]) -> Dict[str, Any]:    raise HTTPException(status_code=401)

    """```

    Extract failure details from event.

    ### 2. Use Environment Variables

    Args:```python

        event: Parsed webhook event# ❌ Bad - Hardcoded secret

        client = GitHubWebhookClient(webhook_secret="hardcoded_secret")

    Returns:

        Dictionary with:# ✅ Good - From environment

        - workflow_name: Name of failed workflowclient = GitHubWebhookClient()  # Uses GITHUB_WEBHOOK_SECRET env var

        - conclusion: failure/cancelled/timed_out```

        - html_url: Link to failed run

        - head_sha: Commit SHA### 3. Constant-Time Comparison

        - head_branch: Branch nameThe client uses `hmac.compare_digest()` to prevent timing attacks.

        - error_message: Error details (if available)

        - started_at: ISO timestamp### 4. Validate Event Types

        - completed_at: ISO timestamp```python

    """# Whitelist expected event types

```ALLOWED_EVENTS = {"workflow_run", "check_run", "push"}



## Examplesevent_type = webhook_client.extract_event_type(headers)

if event_type not in ALLOWED_EVENTS:

### FastAPI Endpoint    return {"error": "Event type not supported"}, 400

```

```python

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks### 5. Rate Limiting

from app.adapters.external.github.webhooks import GitHubWebhookClient```python

from app.core.config import settingsfrom slowapi import Limiter

import loggingfrom slowapi.util import get_remote_address



app = FastAPI()limiter = Limiter(key_func=get_remote_address)

webhook_client = GitHubWebhookClient(secret=settings.GITHUB_WEBHOOK_SECRET)

logger = logging.getLogger(__name__)@app.post("/webhooks/github")

@limiter.limit("100/minute")

@app.post("/api/v1/webhooks/github")async def github_webhook(request: Request):

async def github_webhook(request: Request, background_tasks: BackgroundTasks):    # Process webhook

    """Handle GitHub webhook events."""    pass

    # Get headers```

    signature = request.headers.get("X-Hub-Signature-256")

    event_type = request.headers.get("X-GitHub-Event")## Error Handling

    delivery_id = request.headers.get("X-GitHub-Delivery")

    ### Custom Exceptions

    if not signature or not event_type:

        raise HTTPException(status_code=400, detail="Missing required headers")```python

    from app.adapters.external.github import (

    # Read body    GitHubWebhookError,

    body = await request.body()    WebhookSignatureError,

        WebhookPayloadError,

    try:)

        # Verify and parse

        event = webhook_client.verify_and_parse(body, signature, event_type)try:

            payload = webhook_client.verify_and_parse(body, signature)

        # Log eventexcept WebhookSignatureError:

        logger.info(f"Received {event_type} event: {delivery_id}")    # Invalid signature - potential security issue

            logger.warning("Invalid webhook signature received")

        # Process in background    return {"error": "Unauthorized"}, 401

        if webhook_client.is_workflow_failure(event):except WebhookPayloadError:

            background_tasks.add_task(process_failure, event)    # Malformed payload

            logger.error("Invalid webhook payload")

        return {"status": "received", "delivery_id": delivery_id}    return {"error": "Bad Request"}, 400

        except GitHubWebhookError as e:

    except ValueError as e:    # Other webhook errors

        logger.error(f"Invalid webhook: {e}")    logger.error(f"Webhook error: {e}")

        raise HTTPException(status_code=401, detail=str(e))    return {"error": str(e)}, 500

```

async def process_failure(event: Dict[str, Any]):

    """Process workflow failure in background."""## Testing

    details = webhook_client.extract_failure_details(event)

    ### Unit Tests

    # Create incident

    from app.services.analyzer import AnalyzerService```python

    analyzer = AnalyzerService()import pytest

    from app.adapters.external.github import GitHubWebhookClient

    await analyzer.analyze_failure(

        repository=event["repository"]["full_name"],def test_signature_verification():

        workflow_name=details["workflow_name"],    client = GitHubWebhookClient(webhook_secret="test_secret")

        commit_sha=details["head_sha"],    

        branch=details["head_branch"],    payload = b'{"action": "completed"}'

        error_message=details.get("error_message", ""),    signature = client._compute_signature(payload)

        workflow_url=details["html_url"]    signature_header = f"sha256={signature}"

    )    

```    assert client.verify_signature(payload, signature_header) is True

    assert client.verify_signature(payload, "sha256=invalid") is False

### AWS Lambda Handler

def test_workflow_failure_detection():

```python    client = GitHubWebhookClient(webhook_secret="test")

import json    

from app.adapters.external.github.webhooks import GitHubWebhookClient    payload = {

from app.core.config import settings        "action": "completed",

        "workflow_run": {

webhook_client = GitHubWebhookClient(secret=settings.GITHUB_WEBHOOK_SECRET)            "conclusion": "failure"

        }

def lambda_handler(event, context):    }

    """AWS Lambda handler for GitHub webhooks."""    

    try:    assert client.is_workflow_failure(payload) is True

        # Parse API Gateway event```

        body = event["body"]

        if event.get("isBase64Encoded", False):### Integration Tests

            import base64

            body = base64.b64decode(body)```python

        else:from fastapi.testclient import TestClient

            body = body.encode()import hmac

        import hashlib

        headers = event["headers"]

        signature = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256")def test_webhook_endpoint():

        event_type = headers.get("X-GitHub-Event") or headers.get("x-github-event")    client = TestClient(app)

            

        # Verify and parse    payload = {"action": "completed", "workflow_run": {"conclusion": "failure"}}

        webhook_event = webhook_client.verify_and_parse(body, signature, event_type)    payload_bytes = json.dumps(payload).encode()

            

        # Process failure    # Compute valid signature

        if webhook_client.is_workflow_failure(webhook_event):    secret = os.getenv("GITHUB_WEBHOOK_SECRET").encode()

            details = webhook_client.extract_failure_details(webhook_event)    signature = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()

            # Process asynchronously via SQS/SNS    

            # send_to_queue(details)    response = client.post(

                "/webhooks/github",

        return {        content=payload_bytes,

            "statusCode": 200,        headers={

            "body": json.dumps({"status": "received"})            "X-Hub-Signature-256": f"sha256={signature}",

        }            "X-GitHub-Event": "workflow_run",

                }

    except ValueError as e:    )

        return {    

            "statusCode": 401,    assert response.status_code == 200

            "body": json.dumps({"error": str(e)})```

        }

    except Exception as e:### Local Testing with cURL

        return {

            "statusCode": 500,```bash

            "body": json.dumps({"error": "Internal server error"})# Generate test signature

        }PAYLOAD='{"action":"completed"}'

```SECRET="your_secret"

SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

### Flask Application

# Send webhook

```pythoncurl -X POST http://localhost:8000/webhooks/github \

from flask import Flask, request, jsonify  -H "Content-Type: application/json" \

from app.adapters.external.github.webhooks import GitHubWebhookClient  -H "X-GitHub-Event: workflow_run" \

from app.core.config import settings  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \

  -d "$PAYLOAD"

app = Flask(__name__)```

webhook_client = GitHubWebhookClient(secret=settings.GITHUB_WEBHOOK_SECRET)

## Troubleshooting

@app.route("/webhooks/github", methods=["POST"])

def github_webhook():### Issue: "Invalid signature" errors

    """Handle GitHub webhook."""

    signature = request.headers.get("X-Hub-Signature-256")**Causes:**

    event_type = request.headers.get("X-GitHub-Event")1. Secret mismatch between GitHub and application

    2. Payload modification in transit

    try:3. Wrong encoding (using string instead of bytes)

        event = webhook_client.verify_and_parse(

            request.data,**Solutions:**

            signature,```python

            event_type# Ensure you're using raw bytes, not string

        )body = await request.body()  # ✅ bytes

        # NOT: body = (await request.body()).decode()  # ❌ string

        if webhook_client.is_workflow_failure(event):

            details = webhook_client.extract_failure_details(event)# Check secret matches GitHub webhook settings

            # Process failure...print(f"Using secret: {os.getenv('GITHUB_WEBHOOK_SECRET')[:5]}...")

        ```

        return jsonify({"status": "received"}), 200

        ### Issue: "Missing X-Hub-Signature-256 header"

    except ValueError as e:

        return jsonify({"error": str(e)}), 401GitHub only sends this header if you configured a secret. Ensure webhook secret is set in GitHub settings.

```

### Issue: Signature verification works locally but fails in production

## Testing

Check for:

### Unit Tests- Reverse proxy modifying request body

- Load balancer buffering/transforming requests

```python- Compression middleware interfering

import pytest

from app.adapters.external.github.webhooks import GitHubWebhookClient## Performance Considerations

import json

import hmac- Signature verification is fast (< 1ms typically)

import hashlib- Use async/await for non-blocking I/O

- Consider webhook queues for high-volume scenarios:

@pytest.fixture

def webhook_client():```python

    return GitHubWebhookClient(secret="test_secret")@app.post("/webhooks/github")

async def github_webhook(request: Request, background_tasks: BackgroundTasks):

@pytest.fixture    body = await request.body()

def workflow_failure_payload():    signature = request.headers.get("X-Hub-Signature-256")

    return {    

        "action": "completed",    # Verify synchronously (fast)

        "workflow_run": {    if not verify_github_webhook(body, signature):

            "id": 123,        raise HTTPException(status_code=401)

            "name": "CI",    

            "conclusion": "failure",    # Process asynchronously (slow)

            "head_sha": "abc123",    background_tasks.add_task(process_webhook, body)

            "head_branch": "main",    

            "html_url": "https://github.com/owner/repo/actions/runs/123"    return {"status": "queued"}

        },```

        "repository": {

            "full_name": "owner/repo"## References

        }

    }- [GitHub Webhooks Documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks)

- [Securing Webhooks](https://docs.github.com/en/developers/webhooks-and-events/webhooks/securing-your-webhooks)

def create_signature(payload: dict, secret: str) -> str:- [HMAC Authentication](https://en.wikipedia.org/wiki/HMAC)

    """Create valid HMAC signature."""
    payload_bytes = json.dumps(payload).encode()
    signature = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def test_signature_verification(webhook_client, workflow_failure_payload):
    """Test signature verification."""
    payload_bytes = json.dumps(workflow_failure_payload).encode()
    signature = create_signature(workflow_failure_payload, "test_secret")
    
    assert webhook_client.verify_signature(payload_bytes, signature)

def test_invalid_signature(webhook_client):
    """Test invalid signature rejection."""
    payload = b'{"test": "data"}'
    signature = "sha256=invalid"
    
    assert not webhook_client.verify_signature(payload, signature)

def test_workflow_failure_detection(webhook_client, workflow_failure_payload):
    """Test failure detection."""
    assert webhook_client.is_workflow_failure(workflow_failure_payload)

def test_failure_details_extraction(webhook_client, workflow_failure_payload):
    """Test detail extraction."""
    details = webhook_client.extract_failure_details(workflow_failure_payload)
    
    assert details["workflow_name"] == "CI"
    assert details["conclusion"] == "failure"
    assert details["head_sha"] == "abc123"
    assert details["head_branch"] == "main"
```

### Integration Testing with ngrok

```bash
# 1. Install ngrok
# 2. Start your local server
uvicorn app.main:app --reload --port 8000

# 3. Start ngrok tunnel
ngrok http 8000

# 4. Configure GitHub webhook with ngrok URL
# https://abc123.ngrok.io/api/v1/webhooks/github

# 5. Trigger a workflow failure and check logs
```

### Manual Testing with curl

```bash
# Generate test signature
PAYLOAD='{"action":"completed","workflow_run":{"conclusion":"failure"}}'
SECRET="your_webhook_secret"
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

# Send test webhook
curl -X POST http://localhost:8000/api/v1/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: workflow_run" \
  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
  -d "$PAYLOAD"
```

## Troubleshooting

### Common Issues

#### 1. Signature Verification Fails

**Symptoms:**
- 401 Unauthorized responses
- "Invalid signature" errors in logs

**Solutions:**
```python
# Check if secret matches GitHub configuration
print(f"Secret length: {len(settings.GITHUB_WEBHOOK_SECRET)}")

# Verify payload is raw bytes (not decoded)
body = await request.body()  # FastAPI
# NOT: body = await request.json()

# Check signature header format
signature = request.headers.get("X-Hub-Signature-256")
assert signature.startswith("sha256=")

# Test with known good signature
test_payload = b'{"test": "data"}'
test_secret = "my_secret"
expected_sig = hmac.new(test_secret.encode(), test_payload, hashlib.sha256).hexdigest()
print(f"Expected: sha256={expected_sig}")
```

#### 2. Event Not Detected as Failure

**Symptoms:**
- `is_workflow_failure()` returns False for failed workflows

**Solutions:**
```python
# Check event structure
import json
print(json.dumps(event, indent=2))

# Verify conclusion field
conclusion = event.get("workflow_run", {}).get("conclusion")
print(f"Conclusion: {conclusion}")  # Should be "failure", "cancelled", or "timed_out"

# Check check_run events
if "check_run" in event:
    conclusion = event["check_run"]["conclusion"]
    print(f"Check conclusion: {conclusion}")
```

#### 3. Missing Event Details

**Symptoms:**
- `extract_failure_details()` returns incomplete data

**Solutions:**
```python
# Log full event
logger.debug(f"Full event: {json.dumps(event, indent=2)}")

# Check for required fields
required_fields = ["workflow_run", "repository"]
for field in required_fields:
    if field not in event:
        logger.error(f"Missing field: {field}")

# Handle different event types
if "workflow_run" in event:
    details = webhook_client.extract_failure_details(event)
elif "check_run" in event:
    # Extract from check_run format
    details = {
        "workflow_name": event["check_run"]["name"],
        "conclusion": event["check_run"]["conclusion"],
        # ...
    }
```

#### 4. Duplicate Events

**Symptoms:**
- Same workflow failure processed multiple times

**Solutions:**
```python
# Use delivery ID for deduplication
delivery_id = request.headers.get("X-GitHub-Delivery")

# Check if already processed
from app.adapters.cache.redis import RedisCache
cache = RedisCache()

if await cache.exists(f"webhook:processed:{delivery_id}"):
    return {"status": "duplicate", "delivery_id": delivery_id}

# Mark as processed (expire after 24 hours)
await cache.set(f"webhook:processed:{delivery_id}", "1", expire=86400)
```

### Debugging Tips

1. **Enable verbose logging:**
```python
import logging
logging.getLogger("app.adapters.external.github").setLevel(logging.DEBUG)
```

2. **Log all webhook requests:**
```python
@app.middleware("http")
async def log_webhooks(request: Request, call_next):
    if request.url.path.endswith("/webhooks/github"):
        body = await request.body()
        logger.debug(f"Webhook body: {body.decode()}")
        logger.debug(f"Headers: {dict(request.headers)}")
    return await call_next(request)
```

3. **Test signature generation:**
```python
def test_signature_locally():
    payload = b'{"test": "data"}'
    secret = "your_secret"
    
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    print(f"Signature: sha256={sig}")
    
    # Verify
    client = GitHubWebhookClient(secret=secret)
    assert client.verify_signature(payload, f"sha256={sig}")
```

### GitHub Webhook Logs

Check GitHub's webhook delivery logs:
1. Go to repository Settings → Webhooks
2. Click on your webhook
3. View "Recent Deliveries"
4. Check request/response for each delivery

### Health Check Endpoint

```python
@app.get("/webhooks/github/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    return {
        "status": "healthy",
        "secret_configured": bool(settings.GITHUB_WEBHOOK_SECRET),
        "secret_length": len(settings.GITHUB_WEBHOOK_SECRET) if settings.GITHUB_WEBHOOK_SECRET else 0
    }
```

## Additional Resources

- [GitHub Webhooks Documentation](https://docs.github.com/en/webhooks)
- [Securing Webhooks](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [Webhook Event Payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [Best Practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks)
