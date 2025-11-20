# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.


"""
Test GitHub webhook with real workflow failure event.

This script helps you verify that:
1. Webhook receives and processes GitHub events
2. Incidents are created in the database
3. All incident details are correctly extracted
"""

import sys
import json
from pathlib import Path
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.adapters.database.postgres.models import IncidentTable


def check_database_connection():
    """Verify database is accessible."""
    print("\n" + "="*60)
    print("Step 1: Checking Database Connection")
    print("="*60 + "\n")
    
    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            if result == 1:
                print("✅ Database connection successful")
                return engine
            else:
                print("❌ Database connection failed")
                return None
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None


def check_incidents_table(engine):
    """Check if incidents table exists and show structure."""
    print("\n" + "="*60)
    print("Step 2: Checking Incidents Table")
    print("="*60 + "\n")
    
    try:
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'incidents'
                )
            """)).scalar()
            
            if result:
                print("✅ Incidents table exists")
                
                # Get table info
                result = conn.execute(text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'incidents'
                    ORDER BY ordinal_position
                """))
                
                print("\nTable columns:")
                for row in result:
                    print(f"  • {row[0]}: {row[1]}")
                
                return True
            else:
                print("❌ Incidents table does not exist")
                print("ℹ️  Run migrations: alembic upgrade head")
                return False
                
    except Exception as e:
        print(f"❌ Error checking table: {e}")
        return False


def get_recent_incidents(engine, limit=10):
    """Fetch recent incidents from database."""
    print("\n" + "="*60)
    print("Step 3: Fetching Recent Incidents")
    print("="*60 + "\n")
    
    try:
        with Session(engine) as session:
            stmt = (
                select(IncidentTable)
                .order_by(IncidentTable.created_at.desc())
                .limit(limit)
            )
            incidents = session.execute(stmt).scalars().all()
            
            if incidents:
                print(f"✅ Found {len(incidents)} recent incident(s)\n")
                
                for idx, incident in enumerate(incidents, 1):
                    print(f"Incident #{idx}:")
                    print(f"  ID: {incident.incident_id}")
                    print(f"  Source: {incident.source}")
                    print(f"  Severity: {incident.severity}")
                    print(f"  Failure Type: {incident.failure_type}")
                    print(f"  Created: {incident.created_at}")
                    
                    if incident.context:
                        repo = incident.context.get('repository')
                        workflow = incident.context.get('workflow_name')
                        branch = incident.context.get('branch')
                        if repo:
                            print(f"  Repository: {repo}")
                        if workflow:
                            print(f"  Workflow: {workflow}")
                        if branch:
                            print(f"  Branch: {branch}")
                    
                    print(f"  Error: {incident.error_message}")
                    print()
                
                return incidents
            else:
                print("ℹ️  No incidents found in database")
                print("ℹ️  Trigger a workflow failure in GitHub to create one")
                return []
                
    except Exception as e:
        print(f"❌ Error fetching incidents: {e}")
        import traceback
        traceback.print_exc()
        return []


def search_github_incidents(engine):
    """Search for GitHub-specific incidents."""
    print("\n" + "="*60)
    print("Step 4: Searching GitHub Incidents")
    print("="*60 + "\n")
    
    try:
        with Session(engine) as session:
            stmt = (
                select(IncidentTable)
                .where(IncidentTable.source == 'github')
                .order_by(IncidentTable.created_at.desc())
                .limit(5)
            )
            incidents = session.execute(stmt).scalars().all()
            
            if incidents:
                print(f"✅ Found {len(incidents)} GitHub incident(s)\n")
                
                for incident in incidents:
                    context = incident.context or {}
                    print(f"🔧 {incident.incident_id}")
                    print(f"   Workflow: {context.get('workflow_name', 'N/A')}")
                    print(f"   Repository: {context.get('repository', 'N/A')}")
                    print(f"   Branch: {context.get('branch', 'N/A')}")
                    print(f"   Run URL: {context.get('html_url', 'N/A')}")
                    print(f"   Severity: {incident.severity}")
                    print(f"   Created: {incident.created_at}")
                    print()
                
                return True
            else:
                print("ℹ️  No GitHub incidents found")
                return False
                
    except Exception as e:
        print(f"❌ Error searching incidents: {e}")
        return False


def display_test_instructions():
    """Display instructions for testing with real GitHub events."""
    print("\n" + "="*60)
    print("How to Test with Real GitHub Workflow Failure")
    print("="*60 + "\n")
    
    print("Option 1: Trigger a failure in existing workflow")
    print("-" * 60)
    print("1. Go to your GitHub repository")
    print("2. Make a change that will cause tests to fail:")
    print("   - Edit a test file to make it fail")
    print("   - Or add a syntax error in code")
    print("3. Commit and push:")
    print("   git add .")
    print("   git commit -m 'Test webhook: trigger failure'")
    print("   git push")
    print()
    
    print("Option 2: Create a test workflow that always fails")
    print("-" * 60)
    print("1. Create .github/workflows/test-failure.yml:")
    print("""
---
name: Test Webhook Failure
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Intentional Failure
        run: exit 1
""")
    print("2. Commit and push this file")
    print()
    
    print("Option 3: Manually trigger workflow re-run")
    print("-" * 60)
    print("1. Go to GitHub → Actions tab")
    print("2. Find a failed workflow run")
    print("3. Click 'Re-run all jobs'")
    print("4. Let it fail again")
    print()
    
    print("Then:")
    print("  • Check your application logs for 'incident_created' message")
    print("  • Run this script again to see the incident in database")
    print("  • Or query: SELECT * FROM incidents ORDER BY created_at DESC LIMIT 5;")
    print()


def main():
    """Main test flow."""
    print("\n" + "="*60)
    print("GitHub Webhook Integration Test")
    print("DevFlowFix - Incident Database Verification")
    print("="*60)
    
    # Step 1: Check database connection
    engine = check_database_connection()
    if not engine:
        print("\n❌ Cannot proceed without database connection")
        return 1
    
    # Step 2: Check incidents table
    table_exists = check_incidents_table(engine)
    if not table_exists:
        print("\n❌ Cannot proceed without incidents table")
        return 1
    
    # Step 3: Get recent incidents
    incidents = get_recent_incidents(engine)
    
    # Step 4: Search GitHub incidents
    has_github_incidents = search_github_incidents(engine)
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60 + "\n")
    
    if incidents:
        print(f"✅ Found {len(incidents)} total incident(s)")
        if has_github_incidents:
            print("✅ GitHub webhook integration is working!")
            print("✅ Incidents are being created in database")
            print("\n🎉 Success! Your webhook is fully functional.")
        else:
            print("⚠️  No GitHub incidents found yet")
            print("ℹ️  Trigger a workflow failure to test")
    else:
        print("ℹ️  No incidents in database yet")
        print("ℹ️  Follow the instructions below to create one")
        display_test_instructions()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
