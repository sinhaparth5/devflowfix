# DevFlowFix Testing Guide

Comprehensive testing documentation for the DevFlowFix OAuth integration and analytics features.

## Test Suite Overview

### Test Structure

```
tests/
├── unit/
│   ├── services/
│   │   ├── test_gitlab_oauth.py          # GitLab OAuth provider tests
│   │   ├── test_gitlab_pipeline_tracker.py # Pipeline tracker tests
│   │   ├── test_analytics_service.py     # Analytics service tests
│   │   └── test_token_manager.py         # Token encryption/storage tests
│   └── api/
│       ├── test_gitlab_oauth_endpoints.py # GitLab OAuth API tests
│       ├── test_analytics_endpoints.py   # Analytics API tests
│       └── test_gitlab_webhook.py        # GitLab webhook tests
├── integration/
└── e2e/
```

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-mock

# Or from requirements
pip install -r requirements-dev.txt
```

### Run All Unit Tests

```bash
# Run all unit tests
pytest tests/unit/

# Run with verbose output
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=app --cov-report=html
```

### Run Specific Test Suites

```bash
# OAuth provider tests
pytest tests/unit/services/test_gitlab_oauth.py -v

# Pipeline tracker tests
pytest tests/unit/services/test_gitlab_pipeline_tracker.py -v

# Analytics service tests
pytest tests/unit/services/test_analytics_service.py -v

# Token manager tests
pytest tests/unit/services/test_token_manager.py -v

# API endpoint tests
pytest tests/unit/api/ -v
```

### Run Specific Test Cases

```bash
# Run a specific test class
pytest tests/unit/services/test_gitlab_oauth.py::TestGitLabOAuthProvider -v

# Run a specific test method
pytest tests/unit/services/test_gitlab_oauth.py::TestGitLabOAuthProvider::test_exchange_code_for_token_success -v

# Run tests matching a pattern
pytest tests/unit/ -k "gitlab" -v
```

## Test Coverage

### Current Coverage

| Module | Test File | Test Cases | Coverage |
|--------|-----------|------------|----------|
| GitLab OAuth Provider | test_gitlab_oauth.py | 20+ | ~95% |
| GitLab Pipeline Tracker | test_gitlab_pipeline_tracker.py | 15+ | ~90% |
| Analytics Service | test_analytics_service.py | 15+ | ~90% |
| Token Manager | test_token_manager.py | 20+ | ~95% |
| OAuth API Endpoints | test_gitlab_oauth_endpoints.py | 10+ | ~85% |
| Analytics API Endpoints | test_analytics_endpoints.py | 10+ | ~85% |
| GitLab Webhook | test_gitlab_webhook.py | 10+ | ~85% |

### Generate Coverage Report

```bash
# Generate HTML coverage report
pytest tests/unit/ --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows

# Generate terminal coverage report
pytest tests/unit/ --cov=app --cov-report=term-missing
```

## Test Categories

### 1. Service Layer Tests

#### GitLab OAuth Provider (`test_gitlab_oauth.py`)
Tests for GitLab OAuth 2.0 integration:
- ✅ Provider initialization with custom GitLab URLs
- ✅ Authorization URL generation
- ✅ Token exchange (success/failure)
- ✅ Token refresh
- ✅ Token revocation
- ✅ User info retrieval
- ✅ Project listing and details
- ✅ Webhook (hook) creation/deletion
- ✅ Pipeline operations

```bash
pytest tests/unit/services/test_gitlab_oauth.py -v
```

#### GitLab Pipeline Tracker (`test_gitlab_pipeline_tracker.py`)
Tests for CI/CD pipeline tracking:
- ✅ Status mapping (GitLab → internal)
- ✅ Severity determination
- ✅ Failure summary generation
- ✅ Pipeline event processing
- ✅ Incident auto-creation
- ✅ Pipeline statistics

```bash
pytest tests/unit/services/test_gitlab_pipeline_tracker.py -v
```

#### Analytics Service (`test_analytics_service.py`)
Tests for metrics and analytics:
- ✅ Health score calculation
- ✅ Workflow trends aggregation
- ✅ Repository health metrics
- ✅ Incident trends
- ✅ System health status
- ✅ Time-series grouping

```bash
pytest tests/unit/services/test_analytics_service.py -v
```

#### Token Manager (`test_token_manager.py`)
Tests for OAuth token security:
- ✅ Token encryption/decryption
- ✅ OAuth connection storage
- ✅ Token retrieval
- ✅ Connection revocation
- ✅ Encryption key validation
- ✅ Singleton pattern

```bash
pytest tests/unit/services/test_token_manager.py -v
```

### 2. API Endpoint Tests

#### GitLab OAuth Endpoints (`test_gitlab_oauth_endpoints.py`)
Tests for OAuth API:
- ✅ Authorization flow initiation
- ✅ OAuth callback handling
- ✅ State validation (CSRF protection)
- ✅ Connection retrieval
- ✅ Disconnection/revocation
- ✅ Token refresh

```bash
pytest tests/unit/api/test_gitlab_oauth_endpoints.py -v
```

#### Analytics Endpoints (`test_analytics_endpoints.py`)
Tests for analytics API:
- ✅ Workflow trends endpoint
- ✅ Repository health endpoint
- ✅ Incident trends endpoint
- ✅ System health endpoint
- ✅ Dashboard summary endpoint
- ✅ Error handling

```bash
pytest tests/unit/api/test_analytics_endpoints.py -v
```

#### GitLab Webhook (`test_gitlab_webhook.py`)
Tests for webhook processing:
- ✅ Pipeline event handling
- ✅ Token verification
- ✅ OAuth connection detection
- ✅ Incident creation flow
- ✅ Error handling
- ✅ Invalid payload handling

```bash
pytest tests/unit/api/test_gitlab_webhook.py -v
```

## Continuous Integration

### GitHub Actions

```yaml
# .github/workflows/tests.yml
name: Tests

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
          pip install -r requirements-dev.txt
      - name: Run tests
        run: pytest tests/unit/ --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Test Writing Guidelines

### 1. Test Structure

```python
class TestMyFeature:
    """Test suite for MyFeature."""

    @pytest.fixture
    def my_fixture(self):
        """Create test fixture."""
        return MyObject()

    def test_feature_success(self, my_fixture):
        """Test successful case."""
        result = my_fixture.do_something()
        assert result == expected

    def test_feature_failure(self, my_fixture):
        """Test failure case."""
        with pytest.raises(Exception):
            my_fixture.do_something_bad()
```

### 2. Async Tests

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None
```

### 3. Mocking External APIs

```python
@pytest.mark.asyncio
async def test_with_mock_api():
    """Test with mocked external API."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.json.return_value = {"data": "value"}
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        result = await function_that_calls_api()
        assert result["data"] == "value"
```

### 4. Database Mocking

```python
def test_with_mock_db():
    """Test with mocked database."""
    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_record

    result = function_that_queries_db(mock_db)
    assert result is not None
```

## Best Practices

### ✅ DO
- Write tests for all new features
- Mock external API calls
- Test both success and failure cases
- Use descriptive test names
- Keep tests independent
- Use fixtures for common setup
- Test edge cases
- Verify error messages

### ❌ DON'T
- Make real API calls in unit tests
- Depend on test execution order
- Leave commented-out tests
- Test implementation details
- Mix unit and integration tests
- Ignore failing tests
- Skip error case testing

## Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Error: ModuleNotFoundError
# Solution: Install package in development mode
pip install -e .
```

#### 2. Async Test Failures
```bash
# Error: RuntimeError: Event loop is closed
# Solution: Use @pytest.mark.asyncio decorator
@pytest.mark.asyncio
async def test_my_async_function():
    ...
```

#### 3. Mock Not Working
```bash
# Error: Mock not being called
# Solution: Patch at the correct location
# ✅ Correct
with patch("app.api.v2.oauth.gitlab.get_gitlab_oauth_provider"):
    ...

# ❌ Incorrect
with patch("app.services.oauth.gitlab_oauth.GitLabOAuthProvider"):
    ...
```

## Future Test Plans

### Integration Tests (Planned)
- [ ] End-to-end OAuth flow with test server
- [ ] Database integration tests
- [ ] Real webhook payload processing
- [ ] Multi-provider integration tests

### Performance Tests (Planned)
- [ ] Analytics query performance
- [ ] Concurrent webhook processing
- [ ] Token encryption performance
- [ ] Large dataset handling

### Security Tests (Planned)
- [ ] Token encryption strength
- [ ] CSRF protection validation
- [ ] SQL injection prevention
- [ ] XSS prevention

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py](https://coverage.readthedocs.io/)

## Contact

For questions about testing:
- Check existing tests for examples
- Review this documentation
- Ask in team chat
