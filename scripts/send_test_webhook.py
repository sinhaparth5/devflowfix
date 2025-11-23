# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Send a test webhook payload to verify incident creation."""

import requests
import json
import hmac
import hashlib
import sys
import os
from datetime import datetime

API_BASE_URL = 'http://localhost:8000'
# Read secret from environment or use default
WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', '1zCC4or5bOkGQJYBi8uRUcJVpxvWS3nAoTJ0hYb7RoI')


def get_signature_from_api(payload):
    """Get signature from the signature generation API."""
    try:
        response = requests.post(
            f'{API_BASE_URL}/api/v1/webhook/generate-signature',
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print("Generated signature using API")
            print(f"   Signature: {data['signature'][:32]}...")
            print(f"   Full header: {data['full_header'][:52]}...")
            return data['full_header']
        else:
            print(f"API signature generation failed: {response.status_code}")
            return None
    except requests.exceptions.ConnectionError:
        print("Could not connect to signature API, using local generation")
        return None
    except Exception as e:
        print(f" Error calling signature API: {e}")
        return None


def generate_signature_locally(payload):
    """Generate signature locally using HMAC-SHA256."""
    # Use same JSON serialization as requests will use
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    signature_hash = hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f'sha256={signature_hash}'


def send_test_webhook():
    """Send a test workflow failure webhook."""
    
    # Test payload simulating a workflow failure
    payload = {
        'action': 'completed',
        'workflow_run': {
            'id': 99999,
            'name': 'Manual Test Workflow',
            'conclusion': 'failure',
            'head_branch': 'main',
            'html_url': 'https://github.com/Shine-5705/DevflowFix-tester/actions/runs/99999',
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'status': 'completed',
            'event': 'push'
        },
        'repository': {
            'full_name': 'Shine-5705/DevflowFix-tester',
            'name': 'DevflowFix-tester',
            'owner': {
                'login': 'Shine-5705'
            }
        }
    }
    
    print("="*60)
    print("GitHub Webhook Test - Signature Generation")
    print("="*60)
    print()
    
    # Generate signature using API for accuracy
    payload_json = json.dumps(payload, separators=(',', ':'))
    print("Generating signature using API...")
    
    try:
        sig_response = requests.post(
            f'{API_BASE_URL}/api/v1/webhook/generate-signature',
            data=payload_json,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        if sig_response.status_code == 200:
            sig_data = sig_response.json()
            signature = sig_data['full_header']
            print(f"API signature generated successfully")
            print(f"   Payload size: {sig_data['payload_size']} bytes")
            print(f"   Signature: {sig_data['signature'][:32]}...")
        else:
            print(f"❌ API failed ({sig_response.status_code}), using local generation")
            raise Exception("API failed")
    
    except Exception as e:
        print(f"Falling back to local signature generation")
        payload_bytes = payload_json.encode('utf-8')
        signature_hash = hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
        signature = f'sha256={signature_hash}'
        print(f"   Payload size: {len(payload_bytes)} bytes")
        print(f"   Signature: {signature_hash[:32]}...")
    
    print()
    print("="*60)
    print()
    
    # Send request with exact payload that was signed
    url = f'{API_BASE_URL}/api/v1/webhook/github'
    headers = {
        'X-Hub-Signature-256': signature,
        'X-GitHub-Event': 'workflow_run',
        'Content-Type': 'application/json'
    }
    
    print(f"Sending test webhook to {url}")
    print(f"Event: workflow_run (action: completed, conclusion: failure)")
    print(f"Repository: {payload['repository']['full_name']}")
    print(f"Branch: {payload['workflow_run']['head_branch']}")
    print(f"Signature Header: X-Hub-Signature-256: {signature[:52]}...")
    print()
    
    try:
        # Send with raw JSON string to ensure signature matches
        response = requests.post(url, data=payload_json, headers=headers, timeout=10)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print()
            print("Webhook accepted!")
            print("Check the application logs for:")
            print("   • github_signature_verification - shows signature comparison")
            print("   • github_webhook_received - confirms webhook received")
            print("   • incident_created - confirms incident was created")
            print()
            print("Check database for new incident:")
            print("   python scripts/test_github_webhook.py")
            return 0
        else:
            print()
            print("Webhook failed")
            print("Check logs for signature verification details")
            return 1
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to application")
        print("Make sure FastAPI is running on http://localhost:8000")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(send_test_webhook())
