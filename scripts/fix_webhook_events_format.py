#!/usr/bin/env python3
# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Fix webhook_events format in database.

Converts old format: {"events": ["workflow_run", ...]}
To new format: ["workflow_run", ...]
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.adapters.database.postgres.connection import get_db_connection
from app.adapters.database.postgres.models import RepositoryConnectionTable
import structlog

logger = structlog.get_logger(__name__)


def fix_webhook_events_format():
    """Fix webhook_events format in database."""

    engine = get_db_connection()
    db = Session(engine)

    try:
        # Get all repository connections with webhook_events
        repo_connections = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.webhook_events.isnot(None)
        ).all()

        print(f"\nFound {len(repo_connections)} repositories with webhook_events")

        fixed_count = 0
        skipped_count = 0

        for repo_conn in repo_connections:
            # Check if webhook_events is a dict with "events" key (old format)
            if isinstance(repo_conn.webhook_events, dict) and "events" in repo_conn.webhook_events:
                old_format = repo_conn.webhook_events
                new_format = repo_conn.webhook_events["events"]

                print(f"\n✓ Fixing {repo_conn.repository_full_name}")
                print(f"  Old: {old_format}")
                print(f"  New: {new_format}")

                repo_conn.webhook_events = new_format
                fixed_count += 1

            elif isinstance(repo_conn.webhook_events, list):
                # Already in correct format
                skipped_count += 1
            else:
                print(f"\n⚠️  Unknown format for {repo_conn.repository_full_name}: {repo_conn.webhook_events}")

        # Commit changes
        db.commit()

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total repositories: {len(repo_connections)}")
        print(f"Fixed: {fixed_count}")
        print(f"Already correct: {skipped_count}")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error("fix_webhook_events_failed", error=str(e), exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("WEBHOOK EVENTS FORMAT FIX")
    print("=" * 60)
    print("\nThis script converts webhook_events from:")
    print('  Old: {"events": ["workflow_run", "pull_request", "push"]}')
    print('  New: ["workflow_run", "pull_request", "push"]')
    print()

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Cancelled.")
        sys.exit(0)

    fix_webhook_events_format()
    print("✅ Format fix completed!")
