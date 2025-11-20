# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Verify GitHub webhook setup and configuration.

This script checks:
1. Webhook secret is configured
2. Application endpoint is accessible
3. Signature verification works correctly
4. Webhook payload parsing is functional
"""

import os
import sys
import json
import hmac
import hashlib
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv


# Color output for terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_success(message: str):
    """Print success message in green."""
    print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print error message in red."""
    print(f"{Colors.RED}❌ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.ENDC}")


def print_info(message: str):
    """Print info message in blue."""
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.ENDC}")


def print_header(message: str):
    """Print header message."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")


def check_webhook_secret() -> Optional[str]:
    """Check if webhook secret is configured."""
    print_header("Step 1: Checking Webhook Secret")
    
    # Load .env file
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print_error(f".env file not found at {env_path}")
        print_info("Create .env file from .env.example and set GITHUB_WEBHOOK_SECRET")
        return None
    
    load_dotenv(env_path)
    
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    
    if not webhook_secret:
        print_error("GITHUB_WEBHOOK_SECRET not set in .env file")
        print_info("Generate a secret and add it to .env:")
        print_info("  PowerShell: $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})")
        print_info("  Python: import secrets; print(secrets.token_urlsafe(32))")
        return None
    
    if len(webhook_secret) < 16:
        print_warning(f"Webhook secret is too short ({len(webhook_secret)} chars)")
        print_info("Consider using a longer secret (32+ characters) for better security")
    else:
        print_success(f"Webhook secret configured ({len(webhook_secret)} characters)")
    
    return webhook_secret


def check_endpoint_accessibility(base_url: str = "http://localhost:8000") -> bool:
    """Check if the webhook endpoint is accessible."""
    print_header("Step 2: Checking Endpoint Accessibility")
    
    # Check health endpoint
    try:
        print_info(f"Checking health endpoint: {base_url}/health")
        response = requests.get(f"{base_url}/health", timeout=5)
        
        if response.status_code == 200:
            print_success(f"Health endpoint is accessible")
            print_info(f"Response: {response.json()}")
        else:
            print_warning(f"Health endpoint returned status {response.status_code}")
    
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to {base_url}")
        print_info("Make sure the application is running:")
        print_info("  uvicorn app.main:app --reload --port 8000")
        return False
    
    except requests.exceptions.Timeout:
        print_error("Request timeout")
        return False
    
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False
    
    # Check webhook endpoint exists
    webhook_url = f"{base_url}/webhooks/github"
    try:
        print_info(f"Checking webhook endpoint: {webhook_url}")
        # Send a request without signature (should fail but endpoint should exist)
        response = requests.post(
            webhook_url,
            json={"test": "data"},
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        if response.status_code in [401, 403]:
            print_success("Webhook endpoint exists (rejected unsigned request as expected)")
            return True
        elif response.status_code == 404:
            print_error("Webhook endpoint not found (404)")
            print_info("Ensure /webhooks/github route is configured in app/api/v1/")
            return False
        else:
            print_warning(f"Webhook endpoint returned unexpected status: {response.status_code}")
            return True
    
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to webhook endpoint")
        return False
    
    except Exception as e:
        print_error(f"Error checking webhook endpoint: {e}")
        return False


def compute_signature(payload: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature."""
    return hmac.new(
        key=secret.encode('utf-8'),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()


def test_signature_verification(webhook_secret: str, base_url: str = "http://localhost:8000") -> bool:
    """Test webhook signature verification."""
    print_header("Step 3: Testing Signature Verification")
    
    # Create test payload
    test_payload = {
        "action": "completed",
        "workflow_run": {
            "id": 123456789,
            "name": "Test Workflow",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/test/repo/actions/runs/123456789"
        },
        "repository": {
            "full_name": "test/repo"
        }
    }
    
    payload_bytes = json.dumps(test_payload).encode('utf-8')
    signature = compute_signature(payload_bytes, webhook_secret)
    
    webhook_url = f"{base_url}/webhooks/github"
    
    # Test 1: Valid signature
    print_info("Test 1: Sending request with valid signature...")
    try:
        response = requests.post(
            webhook_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "12345-67890-abcdef"
            },
            timeout=5
        )
        
        if response.status_code == 200:
            print_success("Valid signature accepted (200 OK)")
        elif response.status_code == 202:
            print_success("Valid signature accepted (202 Accepted)")
        else:
            print_warning(f"Unexpected status code: {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
    
    except Exception as e:
        print_error(f"Error testing valid signature: {e}")
        return False
    
    # Test 2: Invalid signature
    print_info("Test 2: Sending request with invalid signature...")
    try:
        response = requests.post(
            webhook_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid_signature_12345",
                "X-GitHub-Event": "workflow_run"
            },
            timeout=5
        )
        
        if response.status_code in [401, 403]:
            print_success(f"Invalid signature rejected ({response.status_code})")
        else:
            print_warning(f"Expected 401/403, got {response.status_code}")
            print_warning("Signature verification may not be working correctly")
    
    except Exception as e:
        print_error(f"Error testing invalid signature: {e}")
        return False
    
    # Test 3: Missing signature
    print_info("Test 3: Sending request without signature...")
    try:
        response = requests.post(
            webhook_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "workflow_run"
            },
            timeout=5
        )
        
        if response.status_code in [401, 403]:
            print_success(f"Missing signature rejected ({response.status_code})")
        else:
            print_warning(f"Expected 401/403, got {response.status_code}")
            print_warning("Requests without signatures should be rejected")
    
    except Exception as e:
        print_error(f"Error testing missing signature: {e}")
        return False
    
    return True


def test_payload_parsing(webhook_secret: str, base_url: str = "http://localhost:8000") -> bool:
    """Test webhook payload parsing."""
    print_header("Step 4: Testing Payload Parsing")
    
    # Load example payload if exists
    example_payload_path = Path(__file__).parent.parent / "examples" / "webhook_payloads" / "workflow_failure.json"
    
    if example_payload_path.exists():
        print_info(f"Loading example payload from {example_payload_path}")
        with open(example_payload_path, 'r') as f:
            test_payload = json.load(f)
    else:
        print_info("Using default test payload")
        test_payload = {
            "action": "completed",
            "workflow_run": {
                "id": 987654321,
                "name": "CI Pipeline",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://github.com/owner/repo/actions/runs/987654321",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "run_started_at": "2025-11-16T10:00:00Z",
                "updated_at": "2025-11-16T10:05:00Z"
            },
            "repository": {
                "full_name": "owner/repo"
            }
        }
    
    payload_bytes = json.dumps(test_payload).encode('utf-8')
    signature = compute_signature(payload_bytes, webhook_secret)
    
    webhook_url = f"{base_url}/webhooks/github"
    
    try:
        print_info("Sending workflow_run event...")
        response = requests.post(
            webhook_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "test-delivery-12345"
            },
            timeout=10
        )
        
        if response.status_code in [200, 202]:
            print_success(f"Payload processed successfully ({response.status_code})")
            
            if response.text:
                try:
                    response_data = response.json()
                    print_info(f"Response: {json.dumps(response_data, indent=2)}")
                except:
                    print_info(f"Response: {response.text[:200]}")
            
            return True
        else:
            print_warning(f"Unexpected status: {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
    
    except Exception as e:
        print_error(f"Error testing payload parsing: {e}")
        return False


def print_configuration_summary():
    """Print configuration summary and next steps."""
    print_header("Configuration Summary")
    
    print_info("Webhook Configuration:")
    print(f"  • Payload URL: https://your-ngrok-url/webhooks/github")
    print(f"  • Content type: application/json")
    print(f"  • Secret: [From .env GITHUB_WEBHOOK_SECRET]")
    print(f"  • Events: Workflow runs, Pushes, Check runs")
    
    print_info("\nTo set up webhook in GitHub:")
    print("  1. Go to: https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks")
    print("  2. Click 'Add webhook'")
    print("  3. Enter the configuration above")
    print("  4. Click 'Add webhook'")
    
    print_info("\nTo test with ngrok:")
    print("  1. Start ngrok: ngrok http 8000")
    print("  2. Copy the HTTPS URL (e.g., https://abc123.ngrok.io)")
    print("  3. Use as Payload URL: https://abc123.ngrok.io/webhooks/github")
    
    print_info("\nMonitoring:")
    print("  • Check logs: tail -f logs/devflowfix.log")
    print("  • View deliveries: GitHub → Settings → Webhooks → Recent Deliveries")
    print("  • Test endpoint: curl http://localhost:8000/health")


def main():
    """Main verification flow."""
    print(f"\n{Colors.BOLD}GitHub Webhook Setup Verification{Colors.ENDC}")
    print(f"{Colors.BOLD}DevFlowFix - CI/CD Failure Detection & Remediation{Colors.ENDC}\n")
    
    # Get base URL from args or use default
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    print_info(f"Using base URL: {base_url}")
    
    # Step 1: Check webhook secret
    webhook_secret = check_webhook_secret()
    if not webhook_secret:
        print_error("\n❌ Webhook secret verification failed")
        print_configuration_summary()
        return 1
    
    # Step 2: Check endpoint accessibility
    if not check_endpoint_accessibility(base_url):
        print_error("\n❌ Endpoint accessibility check failed")
        print_info("Start the application and try again:")
        print_info("  uvicorn app.main:app --reload --port 8000")
        return 1
    
    # Step 3: Test signature verification
    if not test_signature_verification(webhook_secret, base_url):
        print_error("\n❌ Signature verification test failed")
        return 1
    
    # Step 4: Test payload parsing
    if not test_payload_parsing(webhook_secret, base_url):
        print_error("\n❌ Payload parsing test failed")
        return 1
    
    # Success!
    print_header("✅ All Checks Passed!")
    print_success("GitHub webhook setup is correctly configured")
    print_success("You can now set up the webhook in GitHub")
    
    print_configuration_summary()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
