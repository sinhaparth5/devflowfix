# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Generate GitHub webhook signatures using the API.

This script demonstrates how to use the signature generation API
to create valid webhook signatures for testing and integration.
"""

import requests
import json
import sys
from typing import Dict, Any


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")


def get_signature_info(base_url: str = "http://localhost:8000"):
    """Get signature configuration information from the API."""
    print_header("Webhook Signature Configuration Info")
    
    try:
        response = requests.get(
            f"{base_url}/api/v1/webhook/signature-info",
            timeout=5
        )
        
        if response.status_code == 200:
            info = response.json()
            
            print(f"✅ Secret Configured: {info['secret_configured']}")
            print(f"📏 Secret Length: {info['secret_length']} characters")
            print(f"🔐 Algorithm: {info['algorithm']}")
            print(f"📋 Header Name: {info['header_name']}")
            print(f"📝 Header Format: {info['header_format']}")
            print()
            
            print("Example Payload:")
            print(json.dumps(info['example']['payload'], indent=2))
            print()
            
            if info['secret_configured']:
                print(f"Example Signature: {info['example']['signature'][:32]}...")
                print(f"Full Header Value: {info['example']['full_header'][:52]}...")
            else:
                print("⚠️  Cannot generate example signature - secret not configured")
            
            print()
            print("Usage Instructions:")
            for key, value in info['usage_instructions'].items():
                print(f"  {key}: {value}")
            
            return info
        else:
            print(f"❌ Failed to get signature info: {response.status_code}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API")
        print("Make sure the FastAPI server is running on", base_url)
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def generate_signature(payload: Dict[str, Any], base_url: str = "http://localhost:8000"):
    """Generate a signature for the given payload using the API."""
    print_header("Generate Webhook Signature")
    
    print("Payload:")
    payload_json = json.dumps(payload, indent=2)
    print(payload_json)
    print()
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/webhook/generate-signature",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ Signature Generated Successfully!")
            print()
            print(f"📦 Payload Size: {result['payload_size']} bytes")
            print(f"🔑 Payload Hash: {result['payload_hash'][:32]}...")
            print(f"✏️  Signature: {result['signature']}")
            print(f"📋 Full Header: {result['full_header']}")
            print()
            
            print("Usage Example:")
            print(f"  Header Name:  {result['usage']['header_name']}")
            print(f"  Header Value: {result['usage']['header_value'][:70]}...")
            print()
            print("  cURL Example:")
            print(f"    curl -X POST {base_url}/api/v1/webhook/github \\")
            print(f"      -H 'Content-Type: application/json' \\")
            print(f"      -H 'X-GitHub-Event: workflow_run' \\")
            print(f"      -H 'X-Hub-Signature-256: {result['full_header'][:50]}...' \\")
            print(f"      -d '{json.dumps(payload, separators=(',', ':'))[:60]}...'")
            
            return result
        else:
            print(f"❌ Failed to generate signature: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API")
        print("Make sure the FastAPI server is running on", base_url)
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def main():
    """Main function."""
    print_header("GitHub Webhook Signature Generator")
    print("This tool uses the DevFlowFix API to generate webhook signatures.")
    print()
    
    base_url = "http://localhost:8000"
    
    # Step 1: Get signature info
    info = get_signature_info(base_url)
    
    if not info:
        print("\n❌ Could not retrieve signature configuration.")
        print("Make sure the server is running with: uvicorn app.main:app --reload")
        return 1
    
    if not info.get('secret_configured'):
        print("\n❌ Webhook secret is not configured!")
        print("Set the GITHUB_WEBHOOK_SECRET environment variable and restart the server.")
        return 1
    
    # Step 2: Generate signature for a sample payload
    sample_payload = {
        "action": "completed",
        "workflow_run": {
            "id": 123456789,
            "name": "CI Pipeline",
            "conclusion": "failure",
            "status": "completed",
            "head_branch": "main",
            "head_sha": "abc123def456789",
            "html_url": "https://github.com/owner/repo/actions/runs/123456789",
            "run_number": 42,
            "run_attempt": 1,
        },
        "repository": {
            "full_name": "owner/repo",
            "name": "repo",
            "owner": {
                "login": "owner"
            }
        }
    }
    
    result = generate_signature(sample_payload, base_url)
    
    if result:
        print_header("Success!")
        print("✅ You can now use this signature to test webhook integration.")
        print("✅ Check the application logs for signature verification details.")
        print("\n💡 Tip: Run 'python scripts/send_test_webhook.py' to test the full flow.")
        return 0
    else:
        print("\n❌ Failed to generate signature.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
