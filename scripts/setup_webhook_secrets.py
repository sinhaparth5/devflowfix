#!/usr/bin/env python3
"""
Setup Webhook Secrets

This script:
1. Adds the github_webhook_secret column to the users table (if not exists)
2. Generates a webhook secret for existing users who don't have one
3. Displays the secrets for configuration
"""
import os
import sys
import secrets
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def generate_webhook_secret() -> str:
    """Generate a cryptographically secure random webhook secret."""
    random_bytes = secrets.token_bytes(32)  
    secret = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return secret


def add_column_if_not_exists(engine):
    """Add github_webhook_secret column if it doesn't exist."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'github_webhook_secret'
        """))
        
        if result.fetchone() is None:
            print("Adding github_webhook_secret column to users table...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN github_webhook_secret TEXT
            """))
            conn.commit()
            print("Column added successfully")
        else:
            print("Column github_webhook_secret already exists")


def setup_webhook_secret_for_user(engine, user_id: str) -> dict:
    """Generate and store webhook secret for a user."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT user_id, email, github_webhook_secret FROM users WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        user = result.fetchone()
        
        if not user:
            print(f"User '{user_id}' not found")
            return None
        
        existing_secret = user[2]  
        
        if existing_secret:
            print(f"User '{user_id}' already has a webhook secret")
            print(f"   Preview: {existing_secret[:4]}...{existing_secret[-4:]}")
            
            response = input("   Generate a new secret? This will invalidate the old one. (y/N): ")
            if response.lower() != 'y':
                print("   Keeping existing secret")
                return {
                    "user_id": user_id,
                    "email": user[1],
                    "webhook_secret": existing_secret,
                    "is_new": False,
                }
        
        new_secret = generate_webhook_secret()
        
        conn.execute(
            text("""
                UPDATE users 
                SET github_webhook_secret = :secret,
                    updated_at = NOW()
                WHERE user_id = :user_id
            """),
            {"secret": new_secret, "user_id": user_id}
        )
        conn.commit()
        
        print(f"Generated webhook secret for user '{user_id}'")
        
        return {
            "user_id": user_id,
            "email": user[1],
            "webhook_secret": new_secret,
            "is_new": True,
        }


def display_secret_info(user_info: dict):
    """Display the webhook secret and configuration instructions."""
    if not user_info:
        return
    
    secret = user_info["webhook_secret"]
    user_id = user_info["user_id"]
    is_new = user_info.get("is_new", False)
    
    print("\n" + "=" * 80)
    print("GITHUB WEBHOOK SECRET CONFIGURATION")
    print("=" * 80)
    print(f"\nUser: {user_id}")
    print(f"Email: {user_info['email']}")
    print(f"Status: {'Newly Generated' if is_new else 'Existing Secret'}")
    print(f"\nWebhook Secret:\n")
    print(f"   {secret}")
    print(f"\nIMPORTANT: Save this secret now! You won't be able to see it again.")
    print(f"\nCONFIGURATION STEPS:")
    print(f"\n1. Go to your GitHub repository")
    print(f"   → Settings → Webhooks → Add webhook (or edit existing)")
    print(f"\n2. Configure the webhook:")
    print(f"   Payload URL: <your-server>/api/v1/webhook/github")
    print(f"   Content type: application/json")
    print(f"   Secret: {secret}")
    print(f"\n3. Add custom header (IMPORTANT!):")
    print(f"   Unfortunately, GitHub doesn't support custom headers in webhook config.")
    print(f"   Instead, you need to include the user_id in the payload or use a proxy.")
    print(f"\n4. Alternative: Use query parameter (if supported by your setup):")
    print(f"   Payload URL: <your-server>/api/v1/webhook/github?user_id={user_id}")
    print(f"\n5. Select events:")
    print(f"   ☑ Workflow runs")
    print(f"   ☑ Check runs")
    print(f"\n TEST YOUR WEBHOOK:")
    print(f"\n   # Generate test signature:")
    print(f"   curl -X POST 'http://localhost:8000/api/v1/webhook/secret/test?user_id={user_id}' \\")
    print(f"        -H 'Content-Type: application/json' \\")
    print(f"        -d '{{\"test\": \"payload\"}}'")
    print(f"\n   # Send test webhook:")
    print(f"   curl -X POST 'http://localhost:8000/api/v1/webhook/github' \\")
    print(f"        -H 'Content-Type: application/json' \\")
    print(f"        -H 'X-GitHub-Event: ping' \\")
    print(f"        -H 'X-DevFlowFix-User-ID: {user_id}' \\")
    print(f"        -H 'X-Hub-Signature-256: sha256=<signature-from-test-endpoint>' \\")
    print(f"        -d '{{\"test\": \"payload\"}}'")
    print("\n" + "=" * 80 + "\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup webhook secrets for users")
    parser.add_argument("--user-id", help="Specific user ID to setup (default: all users)")
    parser.add_argument("--database-url", help="Database URL (default: from settings)")
    args = parser.parse_args()
    
    if args.database_url:
        database_url = args.database_url
    else:
        database_url = settings.database_url
    
    print(f"🔗 Connecting to database...")
    engine = create_engine(database_url)
    
    add_column_if_not_exists(engine)
    
    if args.user_id:
        user_info = setup_webhook_secret_for_user(engine, args.user_id)
        if user_info:
            display_secret_info(user_info)
    else:
        print("\nFinding users without webhook secrets...")
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT user_id, email 
                FROM users 
                WHERE github_webhook_secret IS NULL 
                ORDER BY created_at
            """))
            users = result.fetchall()
        
        if not users:
            print("All users already have webhook secrets configured")
            return
        
        print(f"Found {len(users)} user(s) without webhook secrets:\n")
        for user in users:
            print(f"  - {user[0]} ({user[1]})")
        
        print("\n")
        response = input(f"Generate secrets for all {len(users)} user(s)? (y/N): ")
        
        if response.lower() == 'y':
            for user in users:
                user_info = setup_webhook_secret_for_user(engine, user[0])
                if user_info:
                    display_secret_info(user_info)
                    input("\nPress Enter to continue to next user...")
    
    print("Setup complete!")


if __name__ == "__main__":
    main()
