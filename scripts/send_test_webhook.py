# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Send a test webhook payload to verify incident creation."""

import requests
import json
import hmac
import hashlib
import sys
from datetime import datetime

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
    
    # Create signature
    payload_bytes = json.dumps(payload).encode('utf-8')
    secret = '1zCC4or5bOkGQJYBi8uRUcJVpxvWS3nAoTJ0hYb7RoI'
    signature = 'sha256=' + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    
    # Send request
    url = 'http://localhost:8000/webhooks/github'
    headers = {
        'X-Hub-Signature-256': signature,
        'X-GitHub-Event': 'workflow_run',
        'Content-Type': 'application/json'
    }
    
    print(f"Sending test webhook to {url}")
    print(f"Event: workflow_run (action: completed, conclusion: failure)")
    print(f"Repository: {payload['repository']['full_name']}")
    print(f"Branch: {payload['workflow_run']['head_branch']}")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        print(f"✅ Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print()
            print("✅ Webhook accepted!")
            print("Check database for new incident:")
            print("  python scripts/test_github_webhook.py")
            return 0
        else:
            print()
            print("❌ Webhook failed")
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
