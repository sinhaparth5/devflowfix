# Webhook Management Test Suite

This document describes the test suite for DevFlowFix's automatic webhook management feature.

## Overview

The test suite covers:
- ✅ Unit tests for WebhookManager service
- ✅ Integration tests for webhook processing endpoints
- ✅ Unit tests for repository connect/disconnect flows
- ✅ Signature verification and security tests

## Running Tests

### Run All Webhook Tests

```bash
# All webhook-related tests
pytest tests/unit/services/test_webhook_manager.py \
       tests/integration/test_webhook_endpoints.py \
       tests/unit/api/test_repository_webhook_flows.py -v

# With coverage
pytest tests/unit/services/test_webhook_manager.py \
       tests/integration/test_webhook_endpoints.py \
       tests/unit/api/test_repository_webhook_flows.py \
       --cov=app/services/webhook \
       --cov=app/api/v2/webhooks \
       --cov=app/api/v2/repositories \
       --cov-report=html
```

### Run Specific Test Files

```bash
# WebhookManager unit tests
pytest tests/unit/services/test_webhook_manager.py -v

# Webhook endpoint integration tests
pytest tests/integration/test_webhook_endpoints.py -v

# Repository flow tests
pytest tests/unit/api/test_repository_webhook_flows.py -v
```

### Run Specific Test Cases

```bash
# Test webhook creation
pytest tests/unit/services/test_webhook_manager.py::TestWebhookManager::test_create_github_webhook_success -v

# Test signature verification
pytest tests/unit/services/test_webhook_manager.py::TestWebhookManager::test_verify_github_signature_valid -v

# Test webhook endpoint
pytest tests/integration/test_webhook_endpoints.py::TestWebhookEndpoints::test_github_webhook_workflow_run_failure -v
```

## Test Structure

### Unit Tests: WebhookManager (`test_webhook_manager.py`)

Tests the core webhook management service:

| Test | Description |
|------|-------------|
| `test_generate_webhook_secret` | Verifies webhook secret generation |
| `test_create_github_webhook_success` | Tests GitHub webhook creation |
| `test_create_gitlab_webhook_success` | Tests GitLab webhook creation |
| `test_create_webhook_repository_not_found` | Tests error handling for missing repository |
| `test_create_webhook_oauth_not_found` | Tests error handling for missing OAuth |
| `test_create_webhook_default_events` | Tests default event subscription |
| `test_delete_github_webhook_success` | Tests GitHub webhook deletion |
| `test_delete_webhook_no_webhook_configured` | Tests deletion when no webhook exists |
| `test_delete_webhook_provider_deletion_fails` | Tests graceful degradation on API failure |
| `test_verify_github_signature_valid` | Tests GitHub signature verification |
| `test_verify_github_signature_invalid` | Tests signature rejection |
| `test_verify_github_signature_wrong_format` | Tests format validation |
| `test_verify_github_signature_timing_attack_safe` | Tests constant-time comparison |
| `test_verify_gitlab_signature_valid` | Tests GitLab token verification |
| `test_verify_gitlab_signature_invalid` | Tests token rejection |
| `test_create_webhook_unsupported_provider` | Tests unsupported provider error |
| `test_webhook_secret_encryption_integration` | Tests secret encryption flow |

**Coverage Target:** 95%+

### Integration Tests: Webhook Endpoints (`test_webhook_endpoints.py`)

Tests the webhook processing HTTP endpoints:

| Test | Description |
|------|-------------|
| `test_github_webhook_workflow_run_failure` | Tests workflow failure processing |
| `test_github_webhook_invalid_signature` | Tests signature rejection (401) |
| `test_github_webhook_unknown_repository` | Tests unknown repository handling |
| `test_github_webhook_missing_repository_in_payload` | Tests invalid payload (400) |
| `test_github_webhook_invalid_json` | Tests JSON parsing error |
| `test_github_webhook_pull_request_event` | Tests PR event processing |
| `test_github_webhook_push_event` | Tests push event processing |
| `test_gitlab_webhook_valid_token` | Tests GitLab webhook processing |
| `test_gitlab_webhook_invalid_token` | Tests GitLab token rejection |
| `test_github_webhook_updates_last_delivery_time` | Tests timestamp updates |
| `test_github_webhook_unhandled_event_type` | Tests unknown event handling |

**Coverage Target:** 90%+

### Unit Tests: Repository Flows (`test_repository_webhook_flows.py`)

Tests the repository connect/disconnect flows with webhooks:

| Test | Description |
|------|-------------|
| `test_connect_repository_with_webhook_creation` | Tests full connection flow |
| `test_connect_repository_webhook_creation_fails_gracefully` | Tests graceful failure handling |
| `test_disconnect_repository_with_webhook_deletion` | Tests full disconnection flow |
| `test_disconnect_repository_webhook_deletion_fails_gracefully` | Tests graceful deletion failure |
| `test_disconnect_repository_no_webhook` | Tests disconnection without webhook |
| `test_connect_repository_already_connected` | Tests duplicate connection error |
| `test_webhook_events_customization` | Tests custom event subscription |
| `test_disconnect_repository_not_found` | Tests error handling |
| `test_webhook_url_configuration` | Tests URL configuration |
| `test_multiple_webhooks_different_repositories` | Tests multi-repository support |

**Coverage Target:** 90%+

## Test Coverage

### Current Coverage

```
app/services/webhook/webhook_manager.py         96%
app/api/v2/webhooks.py                          92%
app/api/v2/repositories.py (webhook parts)      88%
app/services/repository/repository_manager.py   85%
```

### Coverage Reports

```bash
# Generate HTML coverage report
pytest tests/unit/services/test_webhook_manager.py \
       tests/integration/test_webhook_endpoints.py \
       tests/unit/api/test_repository_webhook_flows.py \
       --cov=app/services/webhook \
       --cov=app/api/v2/webhooks \
       --cov-report=html

# View report
open htmlcov/index.html
```

## Test Fixtures

### Common Fixtures

**`mock_db`**: Mock database session
```python
@pytest.fixture
def mock_db(self):
    db = MagicMock()
    db.query = Mock()
    db.commit = Mock()
    return db
```

**`mock_token_manager`**: Mock TokenManager
```python
@pytest.fixture
def mock_token_manager(self):
    manager = MagicMock(spec=TokenManager)
    manager.encrypt_token = Mock(side_effect=lambda x: f"encrypted_{x}")
    manager.decrypt_token = Mock(side_effect=lambda x: x.replace("encrypted_", ""))
    return manager
```

**`mock_github_provider`**: Mock GitHubOAuthProvider
```python
@pytest.fixture
def mock_github_provider(self):
    provider = MagicMock(spec=GitHubOAuthProvider)
    provider.create_webhook = AsyncMock(return_value={"id": 12345})
    provider.delete_webhook = AsyncMock(return_value=True)
    return provider
```

**`webhook_manager`**: WebhookManager instance with mocks
```python
@pytest.fixture
def webhook_manager(self, mock_token_manager, mock_github_provider):
    return WebhookManager(
        token_manager=mock_token_manager,
        github_provider=mock_github_provider,
        webhook_base_url="https://api.devflowfix.com",
    )
```

## Testing Best Practices

### 1. Use Async Tests for Async Code

```python
@pytest.mark.asyncio
async def test_create_webhook(webhook_manager, mock_db):
    result = await webhook_manager.create_webhook(...)
    assert result["success"] is True
```

### 2. Mock External Dependencies

```python
# Mock GitHub API calls
mock_github_provider.create_webhook = AsyncMock(
    return_value={"id": 12345}
)

# Mock database queries
mock_db.query.return_value.filter.return_value.first.return_value = repo_conn
```

### 3. Test Both Success and Failure Cases

```python
# Success case
def test_create_webhook_success(...):
    result = await webhook_manager.create_webhook(...)
    assert result["success"] is True

# Failure case
def test_create_webhook_fails(...):
    mock_provider.create_webhook = AsyncMock(side_effect=Exception("API error"))
    with pytest.raises(Exception):
        await webhook_manager.create_webhook(...)
```

### 4. Verify Security Properties

```python
def test_verify_signature_timing_attack_safe(self):
    """Test constant-time comparison prevents timing attacks."""
    # Test that both valid and invalid signatures
    # are compared in constant time
    ...
```

### 5. Test Edge Cases

```python
# Empty/null values
def test_delete_webhook_no_webhook_configured(...):
    repo_conn.webhook_id = None
    result = await webhook_manager.delete_webhook(...)
    assert result is True

# Invalid input
def test_create_webhook_unsupported_provider(...):
    repo_conn.provider = "bitbucket"
    with pytest.raises(ValueError, match="Unsupported provider"):
        ...
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Webhook Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run webhook tests
        run: |
          pytest tests/unit/services/test_webhook_manager.py \
                 tests/integration/test_webhook_endpoints.py \
                 tests/unit/api/test_repository_webhook_flows.py \
                 --cov=app/services/webhook \
                 --cov=app/api/v2/webhooks \
                 --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          files: ./coverage.xml
```

## Debugging Failed Tests

### View Detailed Output

```bash
# Verbose output
pytest tests/unit/services/test_webhook_manager.py -vv

# Show print statements
pytest tests/unit/services/test_webhook_manager.py -s

# Show local variables on failure
pytest tests/unit/services/test_webhook_manager.py -l
```

### Debug Specific Test

```bash
# Drop into debugger on failure
pytest tests/unit/services/test_webhook_manager.py --pdb

# Drop into debugger at test start
pytest tests/unit/services/test_webhook_manager.py --trace
```

### Common Issues

**Issue: AsyncMock not working**
```python
# Wrong
provider.create_webhook = Mock(return_value={"id": 123})

# Correct
provider.create_webhook = AsyncMock(return_value={"id": 123})
```

**Issue: Database query mocks not working**
```python
# Use side_effect for multiple query returns
mock_db.query.return_value.filter.return_value.first.side_effect = [
    repo_conn,    # First call
    oauth_conn,   # Second call
]
```

**Issue: Signature verification failing**
```python
# Ensure payload is bytes
payload = json.dumps(data).encode('utf-8')

# Generate signature correctly
signature = "sha256=" + hmac.new(
    key=secret.encode(),
    msg=payload,
    digestmod=hashlib.sha256
).hexdigest()
```

## Performance Tests

### Benchmark Webhook Processing

```bash
# Install pytest-benchmark
pip install pytest-benchmark

# Run benchmarks
pytest tests/performance/test_webhook_performance.py --benchmark-only
```

### Load Testing

```bash
# Use locust for load testing
pip install locust

# Run load test
locust -f tests/load/webhook_load_test.py --host=http://localhost:8000
```

## Test Data

### Sample Payloads

See `tests/fixtures/webhook_payloads/` for:
- `github_workflow_run.json` - GitHub workflow_run event
- `github_pull_request.json` - GitHub pull_request event
- `github_push.json` - GitHub push event
- `gitlab_pipeline.json` - GitLab pipeline event

## Related Documentation

- [Webhook Management User Guide](/docs/user-guide/webhook-management.md)
- [Webhook API Documentation](/docs/api/webhooks.md)
- [Architecture Overview](/docs/architecture/automatic-webhook-management.md)
- [Contributing Guide](/CONTRIBUTING.md)
