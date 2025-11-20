# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.


"""Generate a secure webhook secret for GitHub integration."""

import secrets
import sys


def generate_secret(length: int = 32) -> str:
    """
    Generate a cryptographically secure random secret.
    
    Args:
        length: Number of bytes (default: 32)
        
    Returns:
        URL-safe base64 encoded secret string
    """
    return secrets.token_urlsafe(length)


def main():
    """Generate and display webhook secret."""
    print("GitHub Webhook Secret Generator")
    print("=" * 50)
    print()
    
    # Generate secret
    secret = generate_secret(32)
    
    print(f"Generated webhook secret (copy this):")
    print()
    print(f"  {secret}")
    print()
    print("Add this to your .env file:")
    print()
    print(f"  GITHUB_WEBHOOK_SECRET={secret}")
    print()
    print("⚠️  Important Security Notes:")
    print("  • Never commit this secret to version control")
    print("  • Keep .env file in .gitignore")
    print("  • Use the same secret in GitHub webhook settings")
    print("  • Rotate this secret periodically")
    print()


if __name__ == "__main__":
    main()
