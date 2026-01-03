#!/usr/bin/env python3
# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Diagnostic script to check webhook configuration status.

This script checks:
1. Which repositories have webhooks configured
2. Which webhooks are using v1 vs v2 endpoints
3. Which webhooks have secrets configured
4. Webhook health status
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.adapters.database.postgres.connection import get_db_connection
from app.adapters.database.postgres.models import RepositoryConnectionTable
from tabulate import tabulate


def check_webhook_status():
    """Check and display webhook configuration status."""

    # Get database session
    engine = get_db_connection()
    db = Session(engine)

    try:
        # Get all repository connections
        all_repos = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.is_enabled == True
        ).all()

        # Categorize repositories
        repos_with_webhooks = []
        repos_without_webhooks = []
        v1_endpoints = []
        v2_endpoints = []
        missing_secrets = []
        inactive_webhooks = []

        for repo in all_repos:
            if repo.webhook_id:
                repos_with_webhooks.append(repo)

                # Check endpoint version
                if repo.webhook_url:
                    if "/api/v1/webhook/" in repo.webhook_url:
                        v1_endpoints.append(repo)
                    elif "/api/v2/webhooks/" in repo.webhook_url:
                        v2_endpoints.append(repo)

                # Check if secret exists
                if not repo.webhook_secret:
                    missing_secrets.append(repo)

                # Check if inactive
                if repo.webhook_status != "active":
                    inactive_webhooks.append(repo)
            else:
                repos_without_webhooks.append(repo)

        # Print summary
        print("\n" + "=" * 80)
        print("WEBHOOK CONFIGURATION STATUS")
        print("=" * 80 + "\n")

        print(f"Total active repositories: {len(all_repos)}")
        print(f"Repositories with webhooks: {len(repos_with_webhooks)}")
        print(f"Repositories without webhooks: {len(repos_without_webhooks)}\n")

        print("WEBHOOK ENDPOINTS:")
        print(f"  V1 endpoints (/api/v1/webhook/): {len(v1_endpoints)}")
        print(f"  V2 endpoints (/api/v2/webhooks/): {len(v2_endpoints)}\n")

        print("WEBHOOK CONFIGURATION:")
        print(f"  Missing secrets: {len(missing_secrets)}")
        print(f"  Inactive webhooks: {len(inactive_webhooks)}\n")

        # Detailed table
        if repos_with_webhooks:
            print("=" * 80)
            print("DETAILED WEBHOOK STATUS")
            print("=" * 80 + "\n")

            table_data = []
            for repo in repos_with_webhooks:
                # Determine endpoint version
                if repo.webhook_url:
                    if "/api/v1/" in repo.webhook_url:
                        endpoint_version = "v1 ⚠️"
                    elif "/api/v2/" in repo.webhook_url:
                        endpoint_version = "v2 ✓"
                    else:
                        endpoint_version = "unknown"
                else:
                    endpoint_version = "N/A"

                # Check secret
                has_secret = "✓" if repo.webhook_secret else "✗ MISSING"

                # Status
                status = repo.webhook_status or "unknown"
                if status == "active":
                    status = "active ✓"
                elif status == "failed":
                    status = "failed ✗"

                # Last delivery
                if repo.webhook_last_delivery_at:
                    time_diff = datetime.now(timezone.utc) - repo.webhook_last_delivery_at
                    if time_diff.total_seconds() < 3600:  # < 1 hour
                        last_delivery = f"{int(time_diff.total_seconds() / 60)}m ago"
                    elif time_diff.total_seconds() < 86400:  # < 1 day
                        last_delivery = f"{int(time_diff.total_seconds() / 3600)}h ago"
                    else:
                        last_delivery = f"{time_diff.days}d ago"
                else:
                    last_delivery = "never"

                table_data.append([
                    repo.repository_full_name[:40],
                    endpoint_version,
                    has_secret,
                    status,
                    last_delivery,
                    repo.provider,
                ])

            headers = ["Repository", "Endpoint", "Secret", "Status", "Last Delivery", "Provider"]
            print(tabulate(table_data, headers=headers, tablefmt="grid"))
            print()

        # Issues detected
        issues = []
        if v1_endpoints:
            issues.append(f"⚠️  {len(v1_endpoints)} webhooks using v1 endpoints (should migrate to v2)")
        if missing_secrets:
            issues.append(f"⚠️  {len(missing_secrets)} webhooks missing secrets")
        if inactive_webhooks:
            issues.append(f"⚠️  {len(inactive_webhooks)} inactive webhooks")

        if issues:
            print("=" * 80)
            print("ISSUES DETECTED:")
            print("=" * 80)
            for issue in issues:
                print(f"  {issue}")
            print()
            print("To fix these issues, run:")
            print("  python scripts/migrate_webhooks_to_v2.py")
            print()

        # Recommendations
        if v1_endpoints or missing_secrets:
            print("=" * 80)
            print("RECOMMENDATIONS:")
            print("=" * 80)
            print()
            print("1. Run migration script to update webhooks:")
            print("   python scripts/migrate_webhooks_to_v2.py")
            print()
            print("2. Or manually reconnect repositories with issues:")
            print("   - Disconnect: DELETE /api/v2/repositories/connections/{id}")
            print("   - Reconnect: POST /api/v2/repositories/connect")
            print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    try:
        check_webhook_status()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
